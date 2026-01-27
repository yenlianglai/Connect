from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str  # Required - session must exist before chatting
    message: str
    category_ids: list[str] | None = None  # Optional: category IDs to scope search


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    response: str
    retrieved_node_ids: list[str] = []


class CreateTopicRequest(BaseModel):
    """Request model for creating a new learning topic/session."""
    model_config = ConfigDict(from_attributes=True)
    topic_name: str
    parent_category_id: str = "cat_root"
    initial_sub_categories: list[str] | None = None


class CreateTopicResponse(BaseModel):
    """Response model for topic creation."""
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    category_id: str  # The created category node ID (same as session_id)
