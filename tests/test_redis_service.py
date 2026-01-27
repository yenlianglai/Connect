import time

import pytest
import pytest_asyncio
from testcontainers.redis import RedisContainer

from app.services.memory.redis_service import RedisService


@pytest.fixture(scope="module")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest_asyncio.fixture
async def redis_svc(redis_container):
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
    svc = RedisService(url=url)
    yield svc
    await svc.close()


@pytest.mark.asyncio
async def test_session_context(redis_svc):
    session_id = "test_session"
    context = {"last_summary": "Initial summary", "active_topics": ["topic1"]}

    await redis_svc.set_session_context(session_id, context)
    retrieved = await redis_svc.get_session_context(session_id)

    assert retrieved == context
    assert retrieved["active_topics"] == ["topic1"]


@pytest.mark.asyncio
async def test_active_nodes_zset_lru(redis_svc):
    session_id = "lru_session"
    # Add 3 nodes with different timestamps
    now = time.time()
    await redis_svc.add_active_node_id(session_id, "node1", score=now - 10)
    await redis_svc.add_active_node_id(session_id, "node2", score=now)
    await redis_svc.add_active_node_id(session_id, "node3", score=now - 5)

    # node2 should be first (most recent), then node3, then node1
    active_ids = await redis_svc.get_active_node_ids(session_id)
    assert active_ids == ["node2", "node3", "node1"]

    # Prune to max 2 nodes. node1 (oldest) should be gone.
    await redis_svc.prune_active_nodes(session_id, max_nodes=2)
    active_ids_pruned = await redis_svc.get_active_node_ids(session_id)
    assert "node1" not in active_ids_pruned
    assert len(active_ids_pruned) == 2
    assert active_ids_pruned == ["node2", "node3"]


@pytest.mark.asyncio
async def test_knowledge_node_caching(redis_svc):
    node_id = "node_abc"
    node_data = {"id": node_id, "content": "Sample content"}

    await redis_svc.set_knowledge_node(node_id, node_data)
    nodes = await redis_svc.get_knowledge_nodes([node_id, "non_existent"])

    assert len(nodes) == 1
    assert nodes[0]["id"] == node_id
    assert nodes[0]["content"] == "Sample content"
