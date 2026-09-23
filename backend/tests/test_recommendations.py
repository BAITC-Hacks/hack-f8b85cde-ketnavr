from dataclasses import replace
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.calculator import build_recommendations
from app.config import get_settings
from app.data_loader import ProductData
from app.main import app


class RecommendationsTest(unittest.TestCase):
    def setUp(self):
        critical = ProductData(
            code="critical", sku="SKU", product_name="Test product",
            supplier="\u0418\u042d\u041a", category="Electrical", unit="pcs",
            sales_by_month={(2026, month): 304 for month in range(4, 10)},
            stock_qty=0, in_transit_qty=0, moq=1,
            unit_price_kzt=None, lead_time_days=14,
        )
        self.products = [replace(critical, code=f"critical-{i}") for i in range(121)]
        self.products.append(replace(
            critical, code="soon", supplier="SystemElectric", stock_qty=150,
        ))
        self.products.append(replace(critical, code="sufficient", stock_qty=1000))
        self.settings = get_settings().model_copy(update={
            "data_zip_path": Path(__file__), "as_of_date": "2026-09-22",
            "max_recommendations": 0, "safety_stock_days": 14, "ai_provider": "template",
        })
        self.addCleanup(patch.stopall)
        patch("app.main.get_settings", return_value=self.settings).start()
        patch("app.main._load_products_cached", return_value=self.products).start()

    def test_default_config_has_no_recommendation_cap(self):
        with patch.dict(os.environ):
            os.environ.pop("MAX_RECOMMENDATIONS", None)
            self.assertEqual(get_settings.__wrapped__().max_recommendations, 0)

    def test_unlimited_calculation_keeps_soon_rows_and_both_suppliers(self):
        rows = build_recommendations(self.products, "2026-09-22", 14, 0)
        self.assertEqual(len(rows), 122)
        self.assertEqual(sum(row.urgency == "critical" for row in rows), 121)
        self.assertEqual(rows[-1].urgency, "soon")
        self.assertEqual(rows[-1].supplier, "SystemElectric")
        self.assertTrue(all(row.recommended_order_qty > 0 for row in rows))
        limited = build_recommendations(self.products, "2026-09-22", 14, 5)
        self.assertEqual(limited, rows[:5])

    def test_default_endpoint_preserves_complete_calculation(self):
        with TestClient(app) as client:
            response = client.get("/recommendations?ai=false")
            self.assertEqual(response.status_code, 200)
            expected = build_recommendations(self.products, "2026-09-22", 14, 0)
            self.assertEqual(response.json()["recommendations"], [row.model_dump() for row in expected])

    def test_explicit_zero_overrides_legacy_cap_and_positive_limits_still_work(self):
        self.settings.max_recommendations = 120
        with TestClient(app) as client:
            self.assertEqual(len(client.get("/recommendations?ai=false").json()["recommendations"]), 120)
            self.assertEqual(len(client.get("/recommendations?ai=false&limit=0").json()["recommendations"]), 122)
            self.assertEqual(len(client.get("/recommendations?ai=false&limit=5").json()["recommendations"]), 5)
            for value in (-1, 501):
                self.assertEqual(client.get(f"/recommendations?ai=false&limit={value}").status_code, 422)

    def test_summary_counts_all_orders_even_with_configured_cap(self):
        self.settings.max_recommendations = 120
        with TestClient(app) as client:
            result = client.get("/data/summary").json()
            self.assertEqual(result["products_total"], 123)
            self.assertEqual(result["recommendations_total"], 122)
            self.assertEqual(sum(row["recommendations"] for row in result["suppliers"]), 122)
