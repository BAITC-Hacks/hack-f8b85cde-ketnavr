"""Bounded, read-only procurement chat shared by local and presentation APIs."""
from collections import deque
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from time import monotonic

from fastapi import HTTPException

from app.ai_client import _provider_order, answer_procurement_question
from app.config import Settings
from app.models import AssistantChatRequest, AssistantChatResponse, RecommendationsResponse


class ChatLimiter:
    """Per-process global budget; not an authentication or billing system."""
    def __init__(self, max_requests=10, window_seconds=60, max_concurrent=2):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
        self.lock = Lock()
        self.concurrent = BoundedSemaphore(max_concurrent)

    @contextmanager
    def slot(self):
        if not self.concurrent.acquire(blocking=False):
            raise HTTPException(429, "Помощник занят. Повторите вопрос чуть позже.")
        try:
            with self.lock:
                now = monotonic()
                while self.requests and self.requests[0] <= now - self.window_seconds:
                    self.requests.popleft()
                if len(self.requests) >= self.max_requests:
                    raise HTTPException(429, "Слишком много вопросов. Попробуйте через минуту.",
                                        headers={"Retry-After": "60"})
                self.requests.append(now)
            yield
        finally:
            self.concurrent.release()


def answer_chat(payload: AssistantChatRequest, snapshot: RecommendationsResponse,
                settings: Settings) -> AssistantChatResponse:
    if not payload.question.strip():
        raise HTTPException(422, "Введите вопрос помощнику.")
    if not _provider_order(settings):
        raise HTTPException(503, "ИИ-помощник пока не настроен на сервере.")
    try:
        answer = answer_procurement_question(
            payload.question.strip(), [turn.model_dump() for turn in payload.history],
            snapshot.recommendations, snapshot.as_of, settings,
        )
        return AssistantChatResponse(answer=answer)
    except Exception as error:
        raise HTTPException(502, "ИИ временно недоступен. Повторите запрос позже.") from error

