import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from testcontainers.neo4j import Neo4jContainer
from testcontainers.redis import RedisContainer

from app.models.nodes import HorizontalRelationshipType, KnowledgeNode, Relationship, VerticalRelationshipType
from app.services.evolver import MemoryEvolver, MergeDecision
from app.services.graph.neo4j_service import GraphService
from app.services.memory.redis_service import RedisService
from app.services.memory.refresher import MemoryRefresher
from app.services.memory.retriever import MemoryRetriever


@pytest.fixture(scope="module")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5.18.1") as neo4j:
        yield neo4j


@pytest_asyncio.fixture
async def redis_svc(redis_container):
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    svc = RedisService(url=url)
    yield svc
    await svc.close()


@pytest_asyncio.fixture
async def graph_svc(neo4j_container):
    url = neo4j_container.get_connection_url()
    svc = GraphService(uri=url, user="neo4j", password=neo4j_container.password)
    await svc.ensure_vector_index()
    # Mock embedder to avoid real API calls
    with patch.object(svc.embedder, "embed_query", return_value=[0.1] * 768):
        yield svc
    await svc.close()


@pytest.mark.asyncio
async def test_memory_retriever_hybrid_flow(redis_svc, graph_svc):
    retriever = MemoryRetriever(redis_svc=redis_svc, graph_svc=graph_svc)
    session_id = "retriever_session"

    # 1. Seed Neo4j node
    node_id = "node-123"
    node = KnowledgeNode(
        id=node_id,
        tags=["k8s"],
        description="Kubernetes node info",
        content="K8s is a container orchestrator.",
    )
    with patch.object(graph_svc.embedder, "embed_query", return_value=[0.1] * 768):
        await graph_svc.create_knowledge_node(node)

    # 2. Test Cache Miss (fetch from Neo4j)
    # We mock graph_rag_search to return our node
    with patch.object(graph_svc, "graph_rag_search", return_value=[node]):
        context = await retriever.get_relevant_context(session_id, "K8s orchestrator")
        assert "K8s is a container orchestrator" in context

        # Verify it's now in Redis
        active_ids = await redis_svc.get_active_node_ids(session_id)
        assert node_id in active_ids
        cached_nodes = await redis_svc.get_knowledge_nodes([node_id])
        assert cached_nodes[0]["content"] == node.content

    # 3. Test Cache Hit (fetch from Redis)
    # Clear graph_rag_search to ensure it doesn't use it
    with patch.object(graph_svc, "graph_rag_search", return_value=[]):
        context_hit = await retriever.get_relevant_context(session_id, "Something else")
        assert "K8s is a container orchestrator" in context_hit


@pytest.mark.asyncio
async def test_memory_refresher_neighbor_flow(redis_svc, graph_svc):
    refresher = MemoryRefresher(redis_svc=redis_svc, graph_svc=graph_svc, max_active_nodes=2)
    session_id = "refresher_session"

    # 1. Setup A -> B relationship in Neo4j
    node_a = KnowledgeNode(id="A", tags=[], description="A", content="A content")
    node_b = KnowledgeNode(id="B", tags=[], description="B", content="B content")

    with patch.object(graph_svc.embedder, "embed_query", return_value=[0.1] * 768):
        await graph_svc.create_knowledge_node(node_a)
        await graph_svc.create_knowledge_node(node_b)

        rel = Relationship(
            source_id="A", target_id="B", relationship_type=HorizontalRelationshipType.PART_OF, reasoning="A needs B"
        )
        await graph_svc.create_relationship(rel)

    # 2. Add Node A to Redis hot memory
    await redis_svc.add_active_node_id(session_id, "A", score=time.time())

    # 3. Trigger Refresh (should fetch Node B as neighbor)
    await refresher.refresh_hot_memory(session_id)

    # 4. Verify Node B is now active in Redis
    active_ids = await redis_svc.get_active_node_ids(session_id)
    assert "B" in active_ids
    assert "A" in active_ids


@pytest.mark.asyncio
async def test_memory_evolver_dirty_buffer_trigger(redis_svc, graph_svc):
    # Set threshold to 2 for easy testing
    evolver = MemoryEvolver(threshold=2)

    # We need to monkeypatch the global redis_service and graph_service inside the evolver
    with (
        patch("app.services.evolver.redis_service", redis_svc),
        patch("app.services.evolver.graph_service", graph_svc),
        patch("app.services.evolver.invoke_llm_structured") as mock_llm,
    ):
        # 1. Increment buffer once
        await evolver.increment_dirty_buffer("node1")
        assert evolver.is_running == False

        # 2. Increment buffer second time (reaches threshold)
        # Mock LLM to return a "don't merge" decision for now
        mock_llm.return_value = MergeDecision(should_merge=False, reasoning="Not same")

        # We need to mock find_duplicate_candidates to return something or empty
        with patch.object(graph_svc, "find_duplicate_candidates", return_value=[]) as mock_find:
            await evolver.increment_dirty_buffer("node2")

            # Since it's a create_task, we might need a small sleep
            await asyncio.sleep(0.5)

            # Verify dirty nodes were cleared and search was called
            client = await redis_svc.get_client()
            dirty_count = await client.scard("evolver:dirty_nodes")
            assert dirty_count == 0
            mock_find.assert_called_once()
