from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.models import Recommendation, RecommendationsResponse
from app.share import create_app


def snapshot(reason="Calculated explanation"):
    row = Recommendation(
        id="real-1", sku="SKU-1", product_name="Real product", supplier="IEK",
        category="Electrical", stock_qty=2, in_transit_qty=0,
        recommended_order_qty=100, urgency="critical", reason=reason,
    )
    return RecommendationsResponse(as_of="2026-09-22", recommendations=[row])


class SharedPreviewTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dist = Path(self.directory.name) / "dist"
        self.dist.mkdir()
        (self.dist / "index.html").write_text("<html>Shared site</html>", encoding="utf-8")
        (Path(self.directory.name) / ".env").write_text("PRIVATE_SENTINEL", encoding="utf-8")

    def test_visitors_only_read_cached_snapshots_and_keep_calculated_quantities(self):
        enhanced = snapshot("AI explanation of the same calculated order")
        enhanced.recommendations[0].recommended_order_qty = 999
        with patch("app.share._fetch_snapshot", side_effect=[snapshot(), enhanced]) as fetch:
            with TestClient(create_app(self.dist)) as client:
                for _ in range(3):
                    result = client.get("/api/recommendations?ai=true&limit=1")
                    self.assertEqual(result.status_code, 200)
                    row = result.json()["recommendations"][0]
                    self.assertEqual(row["reason"], enhanced.recommendations[0].reason)
                    self.assertEqual(row["recommended_order_qty"], 100)
                    self.assertFalse(row["synthetic"])
                baseline = client.get("/recommendations?ai=false").json()
                self.assertEqual(baseline["recommendations"][0]["reason"], "Calculated explanation")
                self.assertEqual(client.get("/api/health").json()["ai_enriched_rows"], 1)
                self.assertEqual(client.get("/api/recommendations?limit=501").status_code, 422)
                self.assertEqual(fetch.call_count, 2)

    def test_ai_failure_preserves_real_data_and_private_paths_are_not_served(self):
        with patch("app.share._fetch_snapshot", side_effect=[snapshot(), TimeoutError()]):
            with TestClient(create_app(self.dist)) as client:
                self.assertEqual(client.get("/").status_code, 200)
                for path in ("/.env", "/backend/.env", "/api/ai/status", "/docs", "/openapi.json", "/%2e%2e/.env"):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn("PRIVATE_SENTINEL", response.text)
                self.assertEqual(client.post("/api/recommendations").status_code, 405)
                self.assertEqual(client.get("/api/health").json()["ai_enriched_rows"], 0)
                self.assertEqual(client.get("/api/recommendations").json(), snapshot().model_dump())

    def test_missing_backend_does_not_fabricate_demo_data(self):
        with patch("app.share._fetch_snapshot", side_effect=ConnectionError()):
            with self.assertRaises(ConnectionError):
                with TestClient(create_app(self.dist)):
                    pass

    def test_shared_snapshot_keeps_rows_beyond_the_old_120_limit(self):
        baseline = snapshot()
        row = baseline.recommendations[0]
        baseline.recommendations = [row.model_copy(update={"id": f"IEK-{i}"}) for i in range(121)]
        baseline.recommendations.append(row.model_copy(update={
            "id": "SE-soon", "supplier": "SystemElectric", "urgency": "soon",
        }))
        with patch("app.share._fetch_snapshot", side_effect=[baseline, snapshot()]) as fetch:
            with TestClient(create_app(self.dist)) as client:
                result = client.get("/api/recommendations").json()["recommendations"]
                self.assertEqual(len(result), 122)
                self.assertEqual(result[-1]["supplier"], "SystemElectric")
                self.assertEqual(result[-1]["urgency"], "soon")
                self.assertEqual(client.get("/api/health").json()["recommendations"], 122)
                self.assertEqual(fetch.call_args_list[0].kwargs, {"ai": False, "limit": 0, "include_no_order": True})

    def test_full_snapshot_and_order_only_view_share_the_same_cached_facts(self):
        baseline = snapshot()
        baseline.recommendations.insert(0, baseline.recommendations[0].model_copy(update={
            "id": "normal-1", "recommended_order_qty": 0, "urgency": "normal",
            "reason": "Stock is sufficient; no additional order is needed.",
        }))
        with patch("app.share._fetch_snapshot", side_effect=[baseline, snapshot()]) as fetch:
            with TestClient(create_app(self.dist)) as client:
                for ai in ("true", "false"):
                    full = client.get(f"/api/recommendations?include_no_order=true&ai={ai}").json()["recommendations"]
                    self.assertEqual(len(full), 2)
                    self.assertEqual(full[0]["recommended_order_qty"], 0)
                    orders = client.get(f"/api/recommendations?ai={ai}&limit=1").json()["recommendations"]
                    self.assertEqual([row["id"] for row in orders], ["real-1"])
                health = client.get("/api/health").json()
                self.assertEqual(health["recommendations"], 1)
                self.assertEqual(health["calculated_products"], 2)
                self.assertEqual(fetch.call_count, 2)
