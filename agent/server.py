"""sayou-agent — FastAPI server for the reference agent."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sayou.agent.config import get_settings
from sayou.agent.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# ── Singleton ────────────────────────────────────────────────────────

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator(get_settings())
    return _orchestrator


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    logger.info(f"sayou-agent starting on {settings.host}:{settings.port}")
    logger.info(f"Model: {settings.chat_model} | Sandbox: {'enabled' if settings.sandbox_enabled else 'disabled'}")

    orch = get_orchestrator()
    if orch.sandbox_manager:
        await orch.sandbox_manager.start_reaper()

    yield

    logger.info("sayou-agent shutting down")
    await get_orchestrator().shutdown()


# ── App ──────────────────────────────────────────────────────────────

app = FastAPI(title="sayou-agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response ───────────────────────────────────────────────

class MessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[MessageIn]
    session_id: str | None = None
    context_path: str | None = None
    org_id: str = "default"
    user_id: str = "default-user"


# ── Routes ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "sayou-agent"}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        _stream_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_events(request: ChatRequest):
    orchestrator = get_orchestrator()
    session_id = request.session_id or str(uuid4())

    # Extract user message and history
    if not request.messages:
        yield f"data: {json.dumps({'type': 'error', 'message': 'No messages provided'})}\n\n"
        return

    user_message = request.messages[-1].content
    history = [m.model_dump() for m in request.messages[:-1]]

    try:
        async for event in orchestrator.process_message(
            session_id=session_id,
            user_message=user_message,
            history=history,
            org_id=request.org_id,
            user_id=request.user_id,
            context_path=request.context_path,
        ):
            yield f"data: {json.dumps({'type': event.type, **event.data})}\n\n"
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
