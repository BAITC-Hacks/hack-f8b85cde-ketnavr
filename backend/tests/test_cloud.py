from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.cloud import create_app
from app.models import Recommendation


class CloudApiTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.archive = Path(self.directory.name) / "source.zip"
        self.archive.write_bytes(b"PRIVATE_ARCHIVE_SENTINEL")
        self.row = Recommendation(
            id="IEK-1", sku="SKU-1", product_name="Test product", supplier="IEK",
            category="Electrical", stock_qty=2, in_transit_qty=0,
            recommended_order_qty=100, urgency="critical", reason="Calculated explanation",
        )

    def test_complete_calculation_is_cached_and_ai_cannot_trigger_network_calls(self):
        normal = self.row.model_copy(update={"id": "SE-1", "recommended_order_qty": 0, "urgency": "normal"})
        with patch("app.cloud.load_products", return_value=[]) as load:
            with patch("app.cloud.build_recommendations", return_value=[self.row, normal]) as calculate:
                with patch("urllib.request.urlopen", side_effect=AssertionError("No external requests")):
                    with TestClient(create_app(self.archive)) as client:
                        for ai in ("true", "false"):
                            response = client.get(f"/api/recommendations?ai={ai}&include_no_order=true")
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.headers["X-AI-Provider"], "template")
                            self.assertEqual(len(response.json()["recommendations"]), 2)
                            orders = client.get(f"/api/recommendations?ai={ai}").json()["recommendations"]
                            self.assertEqual([row["id"] for row in orders], ["IEK-1"])
                        health = client.get("/api/health").json()
                        self.assertEqual(health["recommendations"], 1)
                        self.assertEqual(health["calculated_products"], 2)
                        self.assertEqual(health["ai_enriched_rows"], 0)
                        self.assertNotIn(str(self.archive), str(health))
                        load.assert_called_once()
                        calculate.assert_called_once()
                        self.assertTrue(calculate.call_args.kwargs["include_no_order"])
                        self.assertEqual(calculate.call_args.kwargs["limit"], 0)

    def test_limit_validation_and_private_routes(self):
        with patch("app.cloud.load_products", return_value=[]):
            with patch("app.cloud.build_recommendations", return_value=[self.row, self.row.model_copy(update={"id": "IEK-2"})]):
                with TestClient(create_app(self.archive)) as client:
                    self.assertEqual(len(client.get("/api/recommendations?limit=1").json()["recommendations"]), 1)
                    for limit in (-1, 501):
                        self.assertEqual(client.get(f"/api/recommendations?limit={limit}").status_code, 422)
                    for path in ("/.env", "/backend/.env", "/backend/data/source.zip", "/api/source.zip", "/api/../backend/data/source.zip", "/docs", "/openapi.json"):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 404)
                        self.assertNotIn("PRIVATE_ARCHIVE_SENTINEL", response.text)
                    self.assertEqual(client.post("/api/recommendations").status_code, 405)

    def test_missing_archive_does_not_return_demo_or_expose_paths(self):
        with TestClient(create_app(self.archive.parent / "missing.zip")) as client:
            for path in ("/api/recommendations", "/api/health"):
                response = client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(str(self.archive.parent), response.text)
                self.assertNotIn("recommendations", response.json())

    def test_parse_errors_are_sanitized(self):
        with patch("app.cloud.load_products", side_effect=ValueError("PRIVATE_DETAIL")):
            with TestClient(create_app(self.archive)) as client:
                response = client.get("/api/recommendations")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("PRIVATE_DETAIL", response.text)
