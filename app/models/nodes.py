from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class VerticalRelationshipType(str, Enum):
    """Relationship types for the structural taxonomy (Vertical Layer)."""
    SUB_CATEGORY_OF = "SUB_CATEGORY_OF"  # Category -> Category
    BELONGS_TO = "BELONGS_TO"            # Knowledge -> Category


class HorizontalRelationshipType(str, Enum):
    """Relationship types for the semantic knowledge web (Horizontal Layer)."""
    # Structural/Logic
    DEFINES = "DEFINES"
    PREREQUISITE_FOR = "PREREQUISITE_FOR"
    PART_OF = "PART_OF"
    IS_A = "IS_A"
    SIMILAR_TO = "SIMILAR_TO"

    # Practical/Experience
    SOLVES = "SOLVES"
    EXAMPLE_OF = "EXAMPLE_OF"
    IMPROVES_ON = "IMPROVES_ON"
    CONTRASTS_WITH = "CONTRASTS_WITH"
    VERIFIES = "VERIFIES"
    RELATED_TO = "RELATED_TO"


class Category(BaseModel):
    """Represents an abstract organizational unit in the taxonomy."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique category ID, e.g., 'cat_backend'")
    name: str = Field(..., description="Human-readable name")
    summary: str = Field(default="", description="LLM-generated abstraction of children")
    level: int = Field(default=0, description="Depth in the tree (0=Root)")
    insert_counter: int = Field(default=0, description="Nodes added since last summarization")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeNode(BaseModel):
    """
    Represents a granular piece of knowledge or experience (Leaf).
    
    Can represent both:
    - Learnable knowledge: technical concepts, solutions, experiences
    - User facts: personal information, preferences, habits (tagged with fact_type tags)
    """
    model_config = ConfigDict(from_attributes=True)

    id: str | None = Field(None, description="System-generated UUID or existing Node ID for consolidation")
    session_id: str | None = Field(None, description="Originating session ID")
    content: str = Field(..., description="Technical details: WHAT problem solved, WHY this approach, and HOW to do it. For facts, this is the fact text.")
    description: str = Field(..., description="LLM's concise summary. For facts, this can be the same as content.")
    tags: list[str] = Field(default_factory=list, description="Keywords for horizontal retrieval. For facts, includes fact_type (identity/preference/habit).")
    worth_of_learning: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance score. Facts default to 1.0.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FactType(str, Enum):
    """Categories for user-specific facts. Used as tags in KnowledgeNode."""
    IDENTITY = "identity"       # Name, role, background, bio
    PREFERENCE = "preference"   # Stable likes, dislikes, technical tool/style choices
    HABIT = "habit"             # Long-term recurring personal behaviors


class Relationship(BaseModel):
    """Represents a directed link between two nodes (Category or Knowledge)."""
    model_config = ConfigDict(from_attributes=True)

    source_id: str = Field(..., description="ID of the source node")
    target_id: str = Field(..., description="ID of the target node")
    relationship_type: VerticalRelationshipType | HorizontalRelationshipType = Field(..., description="Type of the link")
    reasoning: str | None = Field(None, description="Why this link exists")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExtractionResult(BaseModel):
    """Container for all items extracted from a session."""
    knowledge_nodes: list[KnowledgeNode] = Field(default_factory=list, description="Includes both learnable knowledge and user facts")


class NodePlacement(BaseModel):
    """Placement decision for a single node."""
    node_id: str = Field(..., description="The ID of the node to place")
    category_id: str = Field(..., description="ID of existing category, 'NEW_CATEGORY', or 'STAY_HERE'")
    new_category_name: str | None = Field(None, description="Only if category_id is 'NEW_CATEGORY'")
    new_category_summary: str | None = Field(None, description="Broad, abstract summary for the new category")
    reasoning: str

class BatchPlacementResult(BaseModel):
    """Container for multiple placement decisions."""
    placements: list[NodePlacement]


class RelationshipList(BaseModel):
    """Container for a list of relationships, used for LLM structured output."""
    relationships: list[Relationship]
    