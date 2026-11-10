"""FastAPI endpoints for SentinelTrace NuGen AI Assistant.

The route is deliberately thin: it validates and bounds what a client may ask
for, then hands the conversation to `app.assistant`. It never returns a 500 for
a provider problem -- a failure is a 200 with `status: "error"` and a `code`, so
the console can show a sentence rather than a stack trace.

Isolation: this router reads no pipeline state and writes none. It cannot change
a mask, a drift field, a score or an attribution, and no pipeline module imports
it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import assistant

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

# Mirrors the bounds enforced in app.assistant. The browser only ever asks for
# the defaults; the limits exist for everything that is not the browser.
MAX_TOKENS_CAP = assistant.MAX_TOKENS
MAX_TEMPERATURE = assistant.MAX_TEMPERATURE
MAX_MESSAGES = assistant.MAX_MESSAGES
MAX_MESSAGE_CHARS = assistant.MAX_MESSAGE_CHARS


class ChatMessage(BaseModel):
    # `system` is not an accepted role. The safeguard prompt is the server's,
    # and letting a client supply its own is what let the guard be replaced.
    role: Literal["user", "assistant"] = Field(
        default="user", description="Message author role (user or assistant)")
    content: str = Field(
        ..., min_length=1, max_length=MAX_MESSAGE_CHARS,
        description="Message text content")


class ChatRequest(BaseModel):
    messages: Optional[List[ChatMessage]] = Field(
        default=None, max_length=MAX_MESSAGES, description="Conversation message history")
    prompt: Optional[str] = Field(
        default=None, max_length=MAX_MESSAGE_CHARS,
        description="Single prompt (used if messages omitted)")
    max_tokens: int = Field(
        default=400, ge=assistant.MIN_TOKENS, le=MAX_TOKENS_CAP,
        description="Maximum completion tokens")
    temperature: float = Field(
        default=0.3, ge=0.0, le=MAX_TEMPERATURE, description="Sampling temperature")


@router.get("/status")
def get_assistant_status() -> Dict[str, Any]:
    """Return status and configuration of the NuGen AI Assistant.

    Never returns the API key, only whether one is present.
    """
    return assistant.get_status()


@router.post("/chat")
def post_chat(req: ChatRequest) -> Dict[str, Any]:
    """Send conversation messages to the domain AI assistant."""
    msg_list: List[Dict[str, str]] = []
    if req.messages:
        msg_list = [{"role": m.role, "content": m.content} for m in req.messages]
    elif req.prompt and req.prompt.strip():
        msg_list = [{"role": "user", "content": req.prompt.strip()}]

    if not msg_list:
        return {
            "status": "error",
            "code": "no_prompt",
            "reply": "No prompt or message list was provided.",
            "experimental": True,
        }

    return assistant.chat(
        messages=msg_list,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
    )
