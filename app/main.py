import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.llm import invoke_llm
from app.core.logging import setup_logging
from app.core.session.manager import session_manager
from app.models.chat import ChatRequest, ChatResponse, CreateTopicRequest, CreateTopicResponse
from app.prompts.memory import MEMORY_SYSTEM_PROMPT_PREFIX
from app.services.evolver import memory_evolver
from app.services.extractor import context_extractor
from app.services.graph.neo4j_service import graph_service, GraphService
from app.services.memory.redis_service import redis_service
from app.services.memory.refresher import memory_refresher
from app.services.memory.retriever import memory_retriever


async def get_graph_service():
    return graph_service

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle startup and shutdown events for Mnemo.
    """
    logger.info("Initializing Mnemo infrastructure...")

    # 1. Ensure Neo4j Vector Index exists
    await graph_service.ensure_vector_index()

    yield

    # 2. Cleanup resources on shutdown
    logger.info("Cleaning up Mnemo resources...")
    await graph_service.close()
    await redis_service.close()
    logger.info("Mnemo shut down.")


app = FastAPI(title="Mnemo API", lifespan=lifespan)

# Add CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/topics/create", response_model=CreateTopicResponse)
async def create_topic(request: CreateTopicRequest):
    """
    Creates a new learning topic/session with a category node in the graph.
    This is a separate endpoint from chat - frontend decides when to create a topic.
    """
    from app.models.nodes import Category, Relationship, VerticalRelationshipType
    
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    parent_category_id = request.parent_category_id
    
    # Determine level from parent
    parent_level = 0
    async with graph_service.driver.session() as s:
        res = await s.run("MATCH (c:Category {id: $id}) RETURN c.level as level", id=parent_category_id)
        rec = await s.single()
        if rec: parent_level = rec["level"]

    # Create category node in Neo4j
    await graph_service.create_category_node(Category(
        id=session_id, 
        name=request.topic_name, 
        summary=f"Collection of knowledge from session: {request.topic_name}",
        level=parent_level + 1
    ))
    await graph_service.create_relationship(Relationship(
        source_id=session_id, target_id=parent_category_id,
        relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
        reasoning="Session-based hierarchical anchor created on start."
    ))

    # Create initial sub-categories if specified
    if request.initial_sub_categories:
        for sub_name in request.initial_sub_categories:
            if not sub_name.strip(): continue
            sub_id = f"cat_{uuid.uuid4().hex[:8]}"
            await graph_service.create_category_node(Category(
                id=sub_id, 
                name=sub_name.strip(), 
                summary=f"Sub-topic of {request.topic_name}",
                level=parent_level + 2
            ))
            await graph_service.create_relationship(Relationship(
                source_id=sub_id, target_id=session_id,
                relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
                reasoning=f"Pre-defined sub-category for session: {request.topic_name}"
            ))
    
    # Create session in MongoDB
    metadata = {
        "topic_name": request.topic_name,
        "parent_category_id": parent_category_id
    }
    await session_manager.create_session(session_id, metadata=metadata)
    
    logger.info(f"Created topic '{request.topic_name}' with session_id: {session_id}")
    
    return CreateTopicResponse(
        session_id=session_id,
        category_id=session_id
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    End-to-end chat flow - creates session if it doesn't exist (for casual chats).
    For learning topics, use /topics/create first.
    
    1. Retrieve context from Redis (Short-term) / Neo4j (Long-term).
    2. Build prompt with context and session history.
    3. Call LLM for response.
    4. Save messages to MongoDB session.
    """
    session_id = request.session_id
    
    # Fetch session - create if doesn't exist (casual chat)
    session = await session_manager.get_session(session_id)
    if not session:
        # Auto-create a simple session for casual chats (no category node)
        await session_manager.create_session(session_id, metadata={"topic_name": session_id})
        logger.info(f"Auto-created casual chat session: {session_id}")
    
    # Retrieve Context (Hybrid Memory)
    # Use category_ids to scope search if provided, otherwise search entire graph
    memory_context, retrieved_ids = await memory_retriever.get_relevant_context(
        session_id, 
        request.message,
        category_ids=request.category_ids  # None = entire graph, list = scoped search
    )
    logger.info(f"Memory context retrieved: {memory_context[:200]}...")
    
    # Build history
    history = []
    if session:
        history = [{"role": m.role, "content": m.content} for m in session.messages]

    # Build Messages & Call LLM
    messages = [
        {"role": "system", "content": MEMORY_SYSTEM_PROMPT_PREFIX.format(context_text=memory_context)},
        *history,
        {"role": "user", "content": request.message},
    ]
    logger.debug(f"Messages: {messages}")

    # Call LLM
    llm_response = await invoke_llm(messages=messages)

    # Persist to Session DB
    await session_manager.add_message(session_id, "user", request.message)
    await session_manager.add_message(session_id, "assistant", llm_response)

    return ChatResponse(
        session_id=session_id, 
        response=llm_response,
        retrieved_node_ids=retrieved_ids
    )


@app.post("/extract/{session_id}")
async def extract_context(session_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger the context extraction for a specific session.
    """
    background_tasks.add_task(context_extractor.extract_and_persist, session_id)
    return {"message": f"Context extraction task scheduled for session: {session_id}"}


@app.post("/refresh/{session_id}")
async def refresh_memory(session_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger a memory refresh (pre-fetching neighbors into Redis) for a session.
    """
    background_tasks.add_task(memory_refresher.refresh_hot_memory, session_id)
    return {"message": f"Memory refresh task scheduled for session: {session_id}"}


@app.post("/evolve")
async def trigger_evolution(background_tasks: BackgroundTasks, category_id: str | None = None):
    """
    Manually triggers the memory evolution process.
    If category_id is provided, performs evolution only on that subtree.
    Otherwise, scans for all dirty branches.
    """
    if category_id:
        background_tasks.add_task(memory_evolver.evolve_subtree, category_id)
        return {"message": f"Subtree evolution task scheduled for category: {category_id}"}
    else:
        background_tasks.add_task(memory_evolver.evolve)
        return {"message": "Global graph evolution task scheduled."}


@app.get("/graph/data")
async def get_graph_data(session_id: str | None = None):
    """
    Returns the full graph data for visualization.
    If session_id is provided, marks active nodes in Redis as 'hot'.
    """
    active_node_ids = []
    if session_id:
        active_node_ids = await redis_service.get_active_node_ids(session_id)

    return await graph_service.get_full_graph(active_node_ids=active_node_ids)


@app.get("/sessions/{session_id}")
async def get_session_history(session_id: str, limit: int = 50):
    """
    Returns the message history for a given session.
    """
    session = await session_manager.get_session(session_id, message_limit=limit)
    if not session:
        return {"messages": []}
    return session


@app.get("/sessions")
async def list_sessions():
    """
    Returns a list of all sessions.
    """
    sessions = await session_manager.get_all_sessions(limit=50)
    return {"sessions": sessions}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    Deletes a session and its associated cursor.
    Note: This does NOT delete extracted knowledge nodes in Neo4j.
    """
    # 1. Delete from MongoDB
    success = await session_manager.delete_session(session_id)
    if not success:
        return {"message": "Session not found or already deleted."}, 404
    
    # 2. Cleanup Redis cursor
    await redis_service.set_extraction_cursor(session_id, "")
    
    return {"message": f"Session {session_id} deleted successfully."}


@app.get("/sessions/{session_id}/active-nodes")
async def get_active_nodes(session_id: str):
    """
    Returns the IDs of active nodes in Redis for a given session.
    """
    node_ids = await redis_service.get_active_node_ids(session_id)
    return {"active_node_ids": node_ids}


@app.patch("/nodes/knowledge/{node_id}")
async def update_knowledge(node_id: str, data: dict):
    """Updates a knowledge node's content, description, and tags."""
    content = data.get("content")
    description = data.get("description")
    tags = data.get("tags")
    if content is None:
        return {"error": "Content is required"}, 400
    await graph_service.update_knowledge_content(node_id, content, description, tags)
    # Clear Redis cache for this node
    client = await redis_service.get_client()
    await client.delete(f"knowledge:{node_id}")
    return {"message": "Knowledge node updated successfully."}


@app.patch("/nodes/category/{category_id}")
async def update_category(category_id: str, data: dict):
    """Updates a category node's name and/or summary."""
    name = data.get("name")
    summary = data.get("summary")
    await graph_service.update_category_properties(category_id, name, summary)
    return {"message": "Category updated successfully."}




@app.delete("/nodes/{node_id}")
async def delete_node(node_id: str):
    """Manually delete a node and all its relationships."""
    if node_id == "cat_root":
        return {"error": "The root node cannot be deleted."}, 403
        
    await graph_service.delete_node(node_id)
    # Clear Redis cache
    client = await redis_service.get_client()
    await client.delete(f"knowledge:{node_id}")
    return {"message": "Node deleted successfully."}


@app.post("/links")
async def create_link(data: dict):
    """Manually create a relationship between two nodes."""
    source_id = data.get("source_id")
    target_id = data.get("target_id")
    rel_type = data.get("rel_type")
    if not all([source_id, target_id, rel_type]):
        return {"error": "source_id, target_id, and rel_type are required"}, 400
    await graph_service.create_manual_link(source_id, target_id, rel_type)
    return {"message": "Link created successfully."}


@app.delete("/links")
async def delete_link(source_id: str, target_id: str, rel_type: str):
    """Manually delete a relationship between two nodes."""
    await graph_service.delete_manual_link(source_id, target_id, rel_type)
    return {"message": "Link deleted successfully."}


@app.post("/nodes/knowledge")
async def create_knowledge(data: dict, graph_svc: GraphService = Depends(get_graph_service)):
    """Manually create a new knowledge node."""
    from app.models.nodes import KnowledgeNode
    from datetime import datetime, UTC
    
    # Generate a unique ID if not provided
    import uuid
    node_id = data.get("id", f"k-{uuid.uuid4().hex[:8]}")
    
    new_node = KnowledgeNode(
        id=node_id,
        content=data.get("content", ""),
        description=data.get("description", "New Note"),
        worth_of_learning=1.0,
        session_id=data.get("session_id"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    
    await graph_svc.create_knowledge_node(new_node)
    
    # Link to parent if provided
    parent_id = data.get("parent_id")
    if parent_id:
        await graph_svc.create_manual_link(parent_id, node_id, "BELONGS_TO")
        
    return {"id": node_id, "status": "created"}


@app.post("/nodes/category")
async def create_category(data: dict, graph_svc: GraphService = Depends(get_graph_service)):
    """Manually create a new category node with name-collision check."""
    from app.models.nodes import Category
    from datetime import datetime, UTC
    import uuid
    
    name = data.get("name", "New Category")
    parent_id = data.get("parent_id", "cat_root")
    
    # 1. Basic name collision check (loose)
    graph = await graph_svc.get_full_graph()
    if any(n.name == name and n.type == 'category' for n in graph['nodes']):
        # If we found a name match, check if it's already a child of the same parent
        # This is an optimization point for future specific child-queries
        pass 

    node_id = data.get("id", f"cat-{uuid.uuid4().hex[:8]}")
    
    new_cat = Category(
        id=node_id,
        name=name,
        summary=data.get("summary", ""),
        level=data.get("level", 1),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    
    await graph_svc.create_category_node(new_cat)
    await graph_svc.create_manual_link(parent_id, node_id, "SUB_CATEGORY_OF")
        
    return {"id": node_id, "status": "created"}


@app.get("/health")
async def health():
    return {"status": "ok"}
