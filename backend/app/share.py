from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import urllib.request

from fastapi import FastAPI, Query, Request
from fastapi.staticfiles import StaticFiles

from app.models import RecommendationsResponse


logger = logging.getLogger(__name__)
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _fetch_snapshot(backend_url: str, *, ai: bool, limit: int) -> RecommendationsResponse:
    url = f"{backend_url.rstrip('/')}/recommendations?ai={str(ai).lower()}&limit={limit}"
    with urllib.request.urlopen(url, timeout=45) as response:
        return RecommendationsResponse.model_validate_json(response.read())


def create_app(static_dir: Path = FRONTEND_DIST, backend_url: str | None = None) -> FastAPI:
    origin = backend_url or os.getenv("SHARE_BACKEND_URL", "http://127.0.0.1:8000")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not (static_dir / "index.html").is_file():
            raise RuntimeError("Build the frontend with npm run build before starting the shared site.")
        baseline = _fetch_snapshot(origin, ai=False, limit=0)
        reasons = {}
        # Public requests only read these snapshots; they cannot trigger paid API calls.
        try:
            enhanced = _fetch_snapshot(origin, ai=True, limit=3)
            if enhanced.as_of == baseline.as_of:
                reasons = {row.id: row.reason for row in enhanced.recommendations}
        except Exception as error:
            logger.warning("AI snapshot unavailable (%s); using calculated explanations.", type(error).__name__)
        enriched = baseline.model_copy(update={
            "recommendations": [
                row.model_copy(update={"reason": reasons.get(row.id, row.reason)})
                for row in baseline.recommendations
            ]
        })
        application.state.baseline = baseline
        application.state.enriched = enriched
        application.state.created_at = datetime.now(timezone.utc).isoformat()
        application.state.ai_enriched_rows = sum(
            before.reason != after.reason
            for before, after in zip(baseline.recommendations, enriched.recommendations)
        )
        yield

    application = FastAPI(
        title="Ketnavr Shared Preview", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
    )

    @application.get("/api/recommendations", response_model=RecommendationsResponse)
    @application.get("/recommendations", response_model=RecommendationsResponse)
    def recommendations(
        request: Request,
        ai: bool = True,
        limit: int = Query(default=0, ge=0, le=500),
    ) -> RecommendationsResponse:
        snapshot = request.app.state.enriched if ai else request.app.state.baseline
        if limit:
            return snapshot.model_copy(update={"recommendations": snapshot.recommendations[:limit]})
        return snapshot

    @application.get("/api/health")
    @application.get("/health")
    def health(request: Request) -> dict:
        state = request.app.state
        return {
            "status": "ok",
            "mode": "shared_snapshot",
            "as_of": state.baseline.as_of,
            "snapshot_created_at": state.created_at,
            "recommendations": len(state.baseline.recommendations),
            "ai_enriched_rows": state.ai_enriched_rows,
        }

    application.mount("/", StaticFiles(directory=static_dir, html=True, check_dir=False), name="frontend")
    return application


app = create_app()
