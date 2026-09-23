from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.ai_client import enrich_reasons
from app.calculator import build_recommendations
from app.config import get_settings
from app.data_loader import ProductData, load_products
from app.models import (
    AiStatusResponse,
    DataSummaryResponse,
    HealthResponse,
    RecommendationsResponse,
    SupplierSummary,
)


app = FastAPI(title="Ketnavr Supplier Recommendations API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        data_zip_exists=settings.data_zip_path.exists(),
        ai_provider=settings.ai_provider,
        ai_configured=_ai_configured(settings),
        data_source=str(settings.data_zip_path),
    )


@app.get("/recommendations", response_model=RecommendationsResponse)
def recommendations(
    limit: int | None = Query(default=None, ge=0, le=500),
    ai: bool = Query(default=True),
    include_no_order: bool = Query(default=False),
) -> RecommendationsResponse:
    settings = get_settings()
    if not settings.data_zip_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Excel archive not found: {settings.data_zip_path}",
        )
    try:
        products = _load_products_cached(
            str(settings.data_zip_path),
            settings.iek_lead_time_days,
            settings.systeme_lead_time_days,
        )
        rows = build_recommendations(
            products=products,
            as_of=settings.as_of_date,
            safety_stock_days=settings.safety_stock_days,
            limit=settings.max_recommendations if limit is None else limit,
            include_no_order=include_no_order,
        )
        if ai:
            rows = enrich_reasons(rows, settings)
        return RecommendationsResponse(as_of=settings.as_of_date, recommendations=rows)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@lru_cache(maxsize=4)
def _load_products_cached(
    zip_path: str,
    iek_lead_time_days: int,
    systeme_lead_time_days: int,
) -> tuple[ProductData, ...]:
    return tuple(load_products(zip_path, iek_lead_time_days, systeme_lead_time_days))


@app.get("/data/summary", response_model=DataSummaryResponse)
def data_summary() -> DataSummaryResponse:
    settings = get_settings()
    if not settings.data_zip_path.exists():
        raise HTTPException(status_code=500, detail=f"Excel archive not found: {settings.data_zip_path}")
    products = _load_products_cached(
        str(settings.data_zip_path),
        settings.iek_lead_time_days,
        settings.systeme_lead_time_days,
    )
    rows = build_recommendations(
        products=list(products),
        as_of=settings.as_of_date,
        safety_stock_days=settings.safety_stock_days,
        limit=0,
    )
    suppliers = sorted({product.supplier for product in products})
    return DataSummaryResponse(
        as_of=settings.as_of_date,
        data_source=str(settings.data_zip_path),
        products_total=len(products),
        recommendations_total=len(rows),
        suppliers=[
            SupplierSummary(
                supplier=supplier,
                products=sum(1 for product in products if product.supplier == supplier),
                recommendations=sum(1 for row in rows if row.supplier == supplier),
            )
            for supplier in suppliers
        ],
    )


@app.get("/ai/status", response_model=AiStatusResponse)
def ai_status() -> AiStatusResponse:
    settings = get_settings()
    available_providers = _available_providers(settings)
    model = None
    key_present = bool(available_providers)
    if settings.ai_provider == "openai":
        model = settings.openai_model
    elif settings.ai_provider == "nvidia":
        model = settings.nvidia_model
    elif settings.ai_provider == "auto" and len(available_providers) == 1:
        model = settings.openai_model if available_providers[0] == "openai" else settings.nvidia_model
    return AiStatusResponse(
        provider=settings.ai_provider,
        available_providers=available_providers,
        configured=key_present,
        model=model,
        max_rows=settings.ai_max_rows,
        key_present=key_present,
    )


def _ai_configured(settings) -> bool:
    return bool(_available_providers(settings))


def _available_providers(settings) -> list[str]:
    providers = []
    if settings.openai_api_key:
        providers.append("openai")
    if settings.nvidia_api_key:
        providers.append("nvidia")
    if settings.ai_provider == "openai":
        return ["openai"] if settings.openai_api_key else []
    if settings.ai_provider == "nvidia":
        return ["nvidia"] if settings.nvidia_api_key else []
    if settings.ai_provider == "auto":
        return providers
    return []
