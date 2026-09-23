from typing import Literal

from pydantic import BaseModel, Field


Urgency = Literal["critical", "soon", "normal"]


class Recommendation(BaseModel):
    id: str
    sku: str
    product_name: str
    supplier: str
    category: str
    unit: str = "шт."
    stock_qty: float = Field(ge=0)
    in_transit_qty: float = Field(ge=0)
    recommended_order_qty: float = Field(ge=0)
    urgency: Urgency
    reason: str
    avg_daily_demand: float | None = Field(default=None, ge=0)
    coverage_days: float | None = Field(default=None, ge=0)
    lead_time_days: float | None = Field(default=None, ge=0)
    moq: float | None = Field(default=None, ge=0)
    unit_price_kzt: float | None = Field(default=None, ge=0)
    synthetic: bool = False


class RecommendationsResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    as_of: str
    recommendations: list[Recommendation]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    data_zip_exists: bool
    ai_provider: str
    ai_configured: bool
    data_source: str


class SupplierSummary(BaseModel):
    supplier: str
    products: int
    recommendations: int


class DataSummaryResponse(BaseModel):
    as_of: str
    data_source: str
    products_total: int
    recommendations_total: int
    suppliers: list[SupplierSummary]


class AiStatusResponse(BaseModel):
    provider: str
    available_providers: list[str] = Field(default_factory=list)
    configured: bool
    model: str | None
    max_rows: int
    key_present: bool
