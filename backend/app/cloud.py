from functools import lru_cache
import logging
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Query, Response

from app.calculator import build_recommendations
from app.config import get_settings
from app.data_loader import load_products
from app.models import RecommendationsResponse


logger = logging.getLogger(__name__)
ARCHIVE_PATH = Path(__file__).resolve().parents[1] / "data" / "source.zip"


def create_app(archive_path: Path = ARCHIVE_PATH) -> FastAPI:
    application = FastAPI(
        title="Ketnavr Cloud API", docs_url=None, redoc_url=None, openapi_url=None,
    )
    calculation_lock = Lock()

    @lru_cache(maxsize=1)
    def calculate() -> RecommendationsResponse:
        settings = get_settings()
        if not archive_path.is_file():
            raise HTTPException(status_code=503, detail="The server data archive is unavailable.")
        try:
            products = load_products(
                str(archive_path), settings.iek_lead_time_days, settings.systeme_lead_time_days,
            )
            rows = build_recommendations(
                products, settings.as_of_date, settings.safety_stock_days,
                limit=0, include_no_order=True,
            )
            return RecommendationsResponse(as_of=settings.as_of_date, recommendations=rows)
        except Exception as error:
            logger.error("Cloud calculation failed (%s).", type(error).__name__)
            raise HTTPException(status_code=503, detail="The server could not calculate recommendations.") from error

    def snapshot() -> RecommendationsResponse:
        # A cold instance must parse the Excel archive only once, even for concurrent requests.
        with calculation_lock:
            return calculate()

    @application.get("/api/recommendations", response_model=RecommendationsResponse)
    def recommendations(
        response: Response,
        ai: bool = True,
        limit: int = Query(default=0, ge=0, le=500),
        include_no_order: bool = False,
    ) -> RecommendationsResponse:
        baseline = snapshot()
        rows = [row for row in baseline.recommendations if include_no_order or row.recommended_order_qty > 0]
        if limit:
            rows = rows[:limit]
        # Keep the existing query contract, but never call paid AI from the public cloud API.
        response.headers["X-AI-Provider"] = "template"
        response.headers["Cache-Control"] = "public, max-age=0, s-maxage=3600"
        return baseline.model_copy(update={"recommendations": rows})

    @application.get("/api/health")
    def health() -> dict:
        baseline = snapshot()
        return {
            "status": "ok",
            "mode": "cloud_calculation",
            "as_of": baseline.as_of,
            "recommendations": sum(row.recommended_order_qty > 0 for row in baseline.recommendations),
            "calculated_products": len(baseline.recommendations),
            "ai_provider": "template",
            "ai_enriched_rows": 0,
        }

    return application
