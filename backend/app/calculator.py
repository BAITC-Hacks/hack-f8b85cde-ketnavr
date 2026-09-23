from __future__ import annotations

from datetime import date
import math
import statistics

from app.data_loader import ProductData
from app.models import Recommendation


def build_recommendations(
    products: list[ProductData],
    as_of: str,
    safety_stock_days: int,
    limit: int,
) -> list[Recommendation]:
    as_of_date = date.fromisoformat(as_of)
    rows = []
    for product in products:
        row = _recommend_product(product, as_of_date, safety_stock_days)
        if row and row.recommended_order_qty > 0:
            rows.append(row)

    priority = {"critical": 0, "soon": 1, "normal": 2}
    rows.sort(
        key=lambda row: (
            priority[row.urgency],
            -(row.recommended_order_qty or 0),
            row.supplier,
            row.sku,
        )
    )
    return rows[: max(limit, 1)]


def _recommend_product(product: ProductData, as_of_date: date, safety_stock_days: int) -> Recommendation | None:
    recent = _recent_months(product.sales_by_month, as_of_date, 6)
    if not recent or sum(recent) <= 0:
        return None

    cleaned_recent = _clip_outliers(recent)
    avg_monthly = sum(cleaned_recent) / len(cleaned_recent)
    if avg_monthly <= 0:
        return None

    avg_daily = avg_monthly / 30.4
    trend_factor = _trend_factor(cleaned_recent)
    seasonal_factor = _seasonality_factor(product.sales_by_month, as_of_date)
    projected_daily = avg_daily * trend_factor * seasonal_factor
    if projected_daily <= 0:
        return None

    target_days = product.lead_time_days + safety_stock_days
    available_qty = product.stock_qty + product.in_transit_qty
    required_qty = max(projected_daily * target_days - available_qty, 0)
    order_qty = _round_to_moq(required_qty, product.moq)
    coverage_days = available_qty / projected_daily if projected_daily else None
    urgency = _urgency(coverage_days, product.lead_time_days, target_days)

    return Recommendation(
        id=f"{_supplier_prefix(product.supplier)}-{product.code}",
        sku=product.sku,
        product_name=product.product_name,
        supplier=product.supplier,
        category=product.category,
        unit=product.unit or "шт.",
        stock_qty=round(product.stock_qty, 2),
        in_transit_qty=round(product.in_transit_qty, 2),
        recommended_order_qty=round(order_qty, 2),
        urgency=urgency,
        reason=_template_reason(
            product=product,
            avg_daily=projected_daily,
            coverage_days=coverage_days,
            target_days=target_days,
            order_qty=order_qty,
        ),
        avg_daily_demand=round(projected_daily, 2),
        coverage_days=round(coverage_days, 1) if coverage_days is not None else None,
        lead_time_days=float(product.lead_time_days),
        moq=float(product.moq),
        unit_price_kzt=round(product.unit_price_kzt, 2) if product.unit_price_kzt else None,
        synthetic=False,
    )


def _recent_months(values: dict[tuple[int, int], float], as_of_date: date, count: int) -> list[float]:
    eligible = [(key, value) for key, value in values.items() if key <= (as_of_date.year, as_of_date.month)]
    eligible.sort()
    return [value for _, value in eligible[-count:]]


def _clip_outliers(values: list[float]) -> list[float]:
    positives = [value for value in values if value > 0]
    if len(positives) < 4:
        return values
    median = statistics.median(positives)
    if median <= 0:
        return values
    deviations = [abs(value - median) for value in positives]
    mad = statistics.median(deviations) or median * 0.5
    ceiling = median + 3 * mad
    ceiling = max(ceiling, median * 2.5)
    return [min(value, ceiling) for value in values]


def _trend_factor(values: list[float]) -> float:
    if len(values) < 6:
        return 1.0
    previous = sum(values[:3]) / 3
    latest = sum(values[-3:]) / 3
    if previous <= 0:
        return 1.0
    return min(max(latest / previous, 0.85), 1.25)


def _seasonality_factor(values: dict[tuple[int, int], float], as_of_date: date) -> float:
    target_month = as_of_date.month + 1
    target_year = as_of_date.year
    if target_month == 13:
        target_month = 1
        target_year += 1

    same_month_values = [
        value
        for (year, month), value in values.items()
        if month == target_month and year < target_year and value > 0
    ]
    all_values = [value for value in values.values() if value > 0]
    if len(same_month_values) < 2 or len(all_values) < 6:
        return 1.0
    factor = statistics.mean(same_month_values) / statistics.mean(all_values)
    return min(max(factor, 0.8), 1.2)


def _round_to_moq(value: float, moq: float) -> float:
    if value <= 0:
        return 0
    moq = max(float(moq or 1), 1)
    return math.ceil(value / moq) * moq


def _urgency(coverage_days: float | None, lead_time_days: int, target_days: int) -> str:
    if coverage_days is None:
        return "normal"
    if coverage_days < lead_time_days:
        return "critical"
    if coverage_days < target_days:
        return "soon"
    return "normal"


def _template_reason(
    product: ProductData,
    avg_daily: float,
    coverage_days: float | None,
    target_days: int,
    order_qty: float,
) -> str:
    unit = product.unit.rstrip(".")
    coverage_text = "запас не покрывает спрос" if coverage_days is None else f"покрытие около {coverage_days:.1f} дн."
    transit_text = (
        f", в пути {product.in_transit_qty:.0f} {unit}"
        if product.in_transit_qty > 0
        else ", товара в пути нет"
    )
    return (
        f"Средний прогнозный спрос {avg_daily:.2f} {unit}/день, {coverage_text} при сроке поставки "
        f"{product.lead_time_days} дн.{transit_text}. Рекомендуем {order_qty:.0f} {product.unit}: расчёт "
        f"закрывает примерно {target_days} дн. потребности и округлён до MOQ {product.moq:.0f}."
    )


def _supplier_prefix(supplier: str) -> str:
    return "IEK" if supplier == "ИЭК" else "SE"
