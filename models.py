"""Typed shapes for the data. Storage adapters all speak these."""
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    message_id: str
    session_id: str
    seq: int  # order within the session; never rely on timestamps for this
    role: Role
    content: str
    tokens: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class Session(BaseModel):
    session_id: str
    user_id: str
    title: str = "New chat"
    running_summary: str = ""
    summarized_upto: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class User(BaseModel):
    user_id: str
    name: str = ""
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class ChatReply(BaseModel):
    answer: str
    session_id: str
    title: str | None = None
