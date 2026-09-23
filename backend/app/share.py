from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from app.models import AssistantChatRequest, AssistantChatResponse, RecommendationsResponse
from app.assistant import ChatLimiter, answer_chat
from app.config import get_settings


logger = logging.getLogger(__name__)
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _fetch_snapshot(
    backend_url: str, *, ai: bool, limit: int, include_no_order: bool = False,
) -> RecommendationsResponse:
    query = urlencode({"ai": str(ai).lower(), "limit": limit, "include_no_order": str(include_no_order).lower()})
    url = f"{backend_url.rstrip('/')}/recommendations?{query}"
    with urllib.request.urlopen(url, timeout=45) as response:
        return RecommendationsResponse.model_validate_json(response.read())


def create_app(static_dir: Path = FRONTEND_DIST, backend_url: str | None = None, *,
               chat_enabled: bool | None = None) -> FastAPI:
    origin = backend_url or os.getenv("SHARE_BACKEND_URL", "http://127.0.0.1:8000")
    allow_chat = chat_enabled if chat_enabled is not None else os.getenv("SHARE_CHAT_ENABLED", "false").lower() == "true"
    chat_limiter = ChatLimiter()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if not (static_dir / "index.html").is_file():
            raise RuntimeError("Build the frontend with npm run build before starting the shared site.")
        baseline = _fetch_snapshot(origin, ai=False, limit=0, include_no_order=True)
        reasons = {}
        # Recommendation GETs only read snapshots. Optional chat POSTs can call AI.
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
        include_no_order: bool = False,
    ) -> RecommendationsResponse:
        snapshot = request.app.state.enriched if ai else request.app.state.baseline
        rows = [row for row in snapshot.recommendations if include_no_order or row.recommended_order_qty > 0]
        if limit:
            rows = rows[:limit]
        return snapshot.model_copy(update={"recommendations": rows})

    @application.post("/api/assistant/chat", response_model=AssistantChatResponse)
    @application.post("/assistant/chat", response_model=AssistantChatResponse)
    def assistant_chat(payload: AssistantChatRequest, request: Request) -> AssistantChatResponse:
        if not allow_chat:
            raise HTTPException(503, "ИИ-помощник отключён на общей ссылке.")
        with chat_limiter.slot():
            # Chat uses the same server-owned snapshot displayed on the shared site.
            return answer_chat(payload, request.app.state.baseline, get_settings())

    @application.get("/api/health")
    @application.get("/health")
    def health(request: Request) -> dict:
        state = request.app.state
        return {
            "status": "ok",
            "mode": "shared_snapshot",
            "as_of": state.baseline.as_of,
            "snapshot_created_at": state.created_at,
            "recommendations": sum(row.recommended_order_qty > 0 for row in state.baseline.recommendations),
            "calculated_products": len(state.baseline.recommendations),
            "ai_enriched_rows": state.ai_enriched_rows,
            "chat_enabled": allow_chat,
        }

    application.mount("/", StaticFiles(directory=static_dir, html=True, check_dir=False), name="frontend")
    return application


app = create_app()
