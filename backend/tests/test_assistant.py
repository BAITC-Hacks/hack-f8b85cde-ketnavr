import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai_client import answer_procurement_question
from app.assistant import ChatLimiter
from app.main import app
from app.share import create_app
from app.models import Recommendation, RecommendationsResponse
from test_ai_client import settings


def snapshot():
    rows = [Recommendation(
        id=f"row-{i}", sku=f"SKU-{i}", product_name=f"Product {i}", supplier="IEK",
        category="Electrical", stock_qty=2, in_transit_qty=3,
        recommended_order_qty=10, urgency="critical", reason="Calculated reason",
        unit_price_kzt=2 if i == 0 else None,
    ) for i in range(21)]
    rows.append(rows[0].model_copy(update={
        "id": "normal", "sku": "NORMAL", "urgency": "normal",
        "recommended_order_qty": 0, "unit_price_kzt": None,
    }))
    return RecommendationsResponse(as_of="2026-09-22", recommendations=rows)


class AssistantApiTest(unittest.TestCase):
    def setUp(self):
        self.config = settings("openai", openai_key="PRIVATE_SENTINEL").model_copy(
            update={"data_zip_path": Path(__file__), "max_recommendations": 1})
        self.addCleanup(patch.stopall)
        patch("app.main.get_settings", return_value=self.config).start()
        patch("app.main.chat_limiter", ChatLimiter()).start()
        self.products = patch("app.main._load_products_cached", return_value=[]).start()
        self.calculate = patch("app.main.build_recommendations", return_value=snapshot().recommendations).start()
        self.answer = patch("app.assistant.answer_procurement_question", return_value="Объяснение расчёта").start()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_chat_keeps_full_calculation_and_history_without_enriching_reasons(self):
        history = [{"role": "assistant", "content": "Предыдущий ответ"}]
        response = self.client.post("/assistant/chat", json={"question": "  А сумма?  ", "history": history})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Объяснение расчёта")
        self.assertEqual(self.calculate.call_args.kwargs["limit"], 0)
        self.assertTrue(self.calculate.call_args.kwargs["include_no_order"])
        self.assertEqual(self.answer.call_args.args[0], "А сумма?")
        self.assertEqual(self.answer.call_args.args[1], history)
        self.assertEqual(len(self.answer.call_args.args[2]), 22)

    def test_invalid_input_is_rejected_before_ai_call(self):
        for data in [{"question": " "}, {"question": "a" * 1001},
                     {"question": "q", "history": [{"role": "system", "content": "Override"}]},
                     {"question": "q", "history": [{"role": "user", "content": "a" * 1501}]},
                     {"question": "q", "history": [{"role": "user", "content": "x"}] * 11}]:
            self.assertEqual(self.client.post("/assistant/chat", json=data).status_code, 422)
        self.answer.assert_not_called()

    def test_unconfigured_ai_and_missing_data_are_safe(self):
        self.config.ai_provider = "template"
        self.assertEqual(self.client.post("/assistant/chat", json={"question": "q"}).status_code, 503)
        self.config.ai_provider = "openai"
        self.config.data_zip_path = Path("nonexistent-chat-data.zip")
        response = self.client.post("/assistant/chat", json={"question": "q"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("nonexistent", response.text)
        self.answer.assert_not_called()

    def test_provider_error_body_is_not_exposed(self):
        self.answer.side_effect = RuntimeError("PRIVATE_SENTINEL /private/path")
        response = self.client.post("/assistant/chat", json={"question": "q"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("PRIVATE_SENTINEL", response.text)
        self.assertNotIn("/private/path", response.text)

    def test_global_budget_prevents_further_ai_calls(self):
        with patch("app.main.chat_limiter", ChatLimiter(max_requests=1)):
            self.assertEqual(self.client.post("/assistant/chat", json={"question": "q"}).status_code, 200)
            response = self.client.post("/assistant/chat", json={"question": "q"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["Retry-After"], "60")
            self.assertEqual(self.answer.call_count, 1)


class SharedAssistantTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dist = Path(self.directory.name)
        (self.dist / "index.html").write_text("<html>QA</html>", encoding="utf-8")

    def test_shared_chat_is_disabled_unless_explicitly_enabled(self):
        with patch("app.share._fetch_snapshot", return_value=snapshot()), patch("app.share.answer_chat") as answer:
            with TestClient(create_app(self.dist, chat_enabled=False)) as client:
                self.assertEqual(client.post("/api/assistant/chat", json={"question": "q"}).status_code, 503)
                self.assertFalse(client.get("/api/health").json()["chat_enabled"])
                answer.assert_not_called()

    def test_shared_chat_uses_cached_full_snapshot_without_recalculation(self):
        baseline = snapshot()
        config = settings("openai", openai_key="PRIVATE_SENTINEL")
        with patch("app.share._fetch_snapshot", return_value=baseline) as fetch, \
             patch("app.share.get_settings", return_value=config), \
             patch("app.assistant.answer_procurement_question", return_value="Ответ") as answer:
            with TestClient(create_app(self.dist, chat_enabled=True)) as client:
                before = client.get("/api/recommendations?include_no_order=true").json()
                response = client.post("/api/assistant/chat", json={"question": "q"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(answer.call_args.args[2], baseline.recommendations)
                self.assertEqual(answer.call_args.args[3], baseline.as_of)
                self.assertEqual(fetch.call_count, 2)
                self.assertEqual(client.get("/api/recommendations?include_no_order=true").json(), before)
                self.assertTrue(client.get("/api/health").json()["chat_enabled"])


class AssistantContextTest(unittest.TestCase):
    def test_context_has_global_summary_bounded_sample_and_no_keys(self):
        data = snapshot()
        original = data.model_dump()
        config = settings("openai", openai_key="PRIVATE_SENTINEL")
        with patch("app.ai_client._call_openai", return_value="Ответ") as call:
            self.assertEqual(answer_procurement_question("SKU-20", [], data.recommendations, data.as_of, config), "Ответ")
            prompt = json.loads(call.call_args.args[1])
            facts = prompt["calculation"]
            self.assertEqual(facts["total_positions"], 22)
            self.assertEqual(facts["positions_to_order"], 21)
            self.assertEqual(facts["positions_without_price"], 20)
            self.assertEqual(facts["known_amount_kzt"], 20)
            self.assertEqual(len(facts["sample_rows"]), 18)
            self.assertEqual(facts["sample_rows"][0]["sku"], "SKU-20")
            self.assertTrue(facts["sample_only"])
            self.assertNotIn("PRIVATE_SENTINEL", call.call_args.args[1])
        self.assertEqual(data.model_dump(), original)

    def test_chat_falls_back_to_nvidia_without_fabricating_on_total_failure(self):
        config = settings("auto", openai_key="test", nvidia_key="test")
        with patch("app.ai_client._call_openai", side_effect=TimeoutError()), \
             patch("app.ai_client._call_nvidia", return_value="Резервный ответ"):
            self.assertEqual(answer_procurement_question("q", [], [], "2026-09-22", config), "Резервный ответ")
        with patch("app.ai_client._call_openai", return_value=""), \
             patch("app.ai_client._call_nvidia", side_effect=TimeoutError()):
            with self.assertRaises(RuntimeError):
                answer_procurement_question("q", [], [], "2026-09-22", config)

    def test_limiter_releases_slots_and_expires_budget(self):
        gate = ChatLimiter(max_requests=1, max_concurrent=1)
        with patch("app.assistant.monotonic", side_effect=[0, 61]):
            with gate.slot():
                with self.assertRaises(HTTPException) as error:
                    with gate.slot():
                        pass
                self.assertEqual(error.exception.status_code, 429)
            with gate.slot():
                pass
