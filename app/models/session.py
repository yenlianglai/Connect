from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat import ChatMessage


class SessionMessage(ChatMessage):
    """Extends ChatMessage with a timestamp for storage."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Session(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    session_id: str = Field(..., alias="_id")
    messages: list[SessionMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
