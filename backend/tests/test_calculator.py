import unittest

from app.calculator import build_recommendations
from app.data_loader import ProductData


class CalculatorTest(unittest.TestCase):
    def test_recommendation_rounds_to_moq_and_marks_critical(self):
        product = ProductData(
            code="T-001",
            sku="SKU-001",
            product_name="Тестовый автомат",
            supplier="ИЭК",
            category="Автоматика",
            unit="шт.",
            sales_by_month={
                (2026, 4): 300,
                (2026, 5): 300,
                (2026, 6): 300,
                (2026, 7): 300,
                (2026, 8): 300,
                (2026, 9): 300,
            },
            stock_qty=10,
            in_transit_qty=0,
            moq=12,
            unit_price_kzt=None,
            lead_time_days=14,
        )

        rows = build_recommendations([product], "2026-09-22", safety_stock_days=14, limit=10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].urgency, "critical")
        self.assertEqual(rows[0].recommended_order_qty % 12, 0)
        self.assertIn("MOQ 12", rows[0].reason)


if __name__ == "__main__":
    unittest.main()
