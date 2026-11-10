"""FastAPI endpoints for SentinelTrace NuGen AI Assistant."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import assistant

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str = Field(default="user", description="Message author role (user, assistant, system)")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    messages: Optional[List[ChatMessage]] = Field(default=None, description="Conversation message history")
    prompt: Optional[str] = Field(default=None, description="Single prompt (used if messages omitted)")
    max_tokens: Optional[int] = Field(default=400, description="Maximum completion tokens")
    temperature: Optional[float] = Field(default=0.3, description="Sampling temperature")


@router.get("/status")
def get_assistant_status() -> Dict[str, Any]:
    """Return status and configuration of the NuGen AI Assistant."""
    return assistant.get_status()


@router.post("/chat")
def post_chat(req: ChatRequest) -> Dict[str, Any]:
    """Send conversation messages to the domain AI assistant."""
    msg_list: List[Dict[str, str]] = []
    if req.messages:
        msg_list = [{"role": m.role, "content": m.content} for m in req.messages]
    elif req.prompt:
        msg_list = [{"role": "user", "content": req.prompt}]
    else:
        return {
            "status": "error",
            "reply": "No prompt or message list was provided.",
            "experimental": True,
        }

    return assistant.chat(
        messages=msg_list,
        max_tokens=req.max_tokens or 400,
        temperature=req.temperature if req.temperature is not None else 0.3,
    )
