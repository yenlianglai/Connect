import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.neo4j import Neo4jContainer
from testcontainers.redis import RedisContainer

from app.core.llm import invoke_llm
from app.core.logging import setup_logging
from app.core.session.manager import SessionManager
from app.models.nodes import Category, Relationship, VerticalRelationshipType
from app.services.evolver import MemoryEvolver
from app.services.extractor import ContextExtractor
from app.services.graph.neo4j_service import GraphService
from app.services.memory.redis_service import RedisService
from app.services.memory.refresher import MemoryRefresher
from app.services.memory.retriever import MemoryRetriever

# Initialize logging for the test
setup_logging()
logger = logging.getLogger("it-test")


@pytest.fixture(scope="module")
def infra():
    """
    DEBUG VERSION: Uses local docker-compose infrastructure instead of temporary containers.
    """
    logger.info("Using LIVE infrastructure (localhost)...")
    yield {
        "mongodb_url": "mongodb://admin:password@localhost:27017",
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "password",  # Change if you set a different password
        "redis_url": "redis://localhost:6379",
    }


@pytest.mark.asyncio
async def test_end_to_end_memory_lifecycle(infra):
    """
    Tests the full lifecycle:
    1. Seed Taxonomy
    2. Batch 1: Chat -> Extract -> Retrieve
    3. Batch 2: Chat -> Extract -> Evolve -> Retrieve
    4. Final Recall Verification
    """
    # 1. Initialize Services with test containers
    session_mgr = SessionManager(mongodb_url=infra["mongodb_url"], db_name="it_test_db")
    graph_svc = GraphService(uri=infra["neo4j_uri"], user=infra["neo4j_user"], password=infra["neo4j_password"])
    redis_svc = RedisService(url=infra["redis_url"])

    # 2. Setup Memory Components with injected services
    refresher = MemoryRefresher(redis_svc=redis_svc, graph_svc=graph_svc)
    evolver = MemoryEvolver(graph_svc=graph_svc, redis_svc=redis_svc, threshold=1)
    retriever = MemoryRetriever(redis_svc=redis_svc, graph_svc=graph_svc)

    # ContextExtractor needs the local evolver/refresher to avoid using global ones
    extractor = ContextExtractor(
        graph_svc=graph_svc, session_mgr=session_mgr, redis_svc=redis_svc, evolver=evolver, refresher=refresher
    )

    # 3. Seed Taxonomy (Mandatory)
    await graph_svc.ensure_vector_index()
    root = Category(id="cat_root", name="Root", summary="Root", level=0)
    await graph_svc.create_category_node(root)

    # Initial Level 1 Categories
    cat_se = Category(
        id="cat_se", name="Software Engineering", summary="Software engineering principles and practices", level=1
    )
    await graph_svc.create_category_node(cat_se)
    await graph_svc.create_relationship(
        Relationship(
            source_id="cat_se", target_id="cat_root", relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF
        )
    )

    # 4. Prepare Message Data
    with open("tests/data/messages.json") as f:
        data = json.load(f)

    # Batch 1: HR Chatbot discussion (Messages 0-20)
    batch_1 = data["messages"][0:20]
    # Batch 2: Redis/NoSQL discussion (Messages 20-40)
    batch_2 = data["messages"][20:40]

    session_id = f"it-session-{uuid.uuid4().hex[:6]}"

    # --- ITERATION 1: HR CHATBOT ---
    logger.info(f"🚀 ITERATION 1: Injecting messages for session {session_id}...")
    for msg in batch_1:
        text = msg.get("text")
        if not text:
            continue
        if "Updated room membership" in text:
            continue
        role = "user" if msg["creator"]["user_type"] == "Human" else "assistant"
        content = f"{msg['creator']['name']}: {text}"
        await session_mgr.add_message(session_id, role, content)

    # Verify messages are in DB
    saved_session = await session_mgr.get_session(session_id)
    assert saved_session is not None and len(saved_session.messages) > 0
    logger.info(f"✅ Saved {len(saved_session.messages)} messages to session DB.")

    time.sleep(5)  # Wait before first extraction
    logger.info("🧠 Running Context Extraction for Batch 1...")
    # Even though we passed services to extractor, we still patch global services
    # just in case some other module uses them (like evolver.py uses graph_service globally).
    with (
        patch("app.services.extractor.graph_service", graph_svc),
        patch("app.services.extractor.session_manager", session_mgr),
        patch("app.services.extractor.redis_service", redis_svc),
        patch("app.services.evolver.graph_service", graph_svc),
        patch("app.services.evolver.redis_service", redis_svc),
        patch("app.services.memory.retriever.graph_service", graph_svc),
        patch("app.services.memory.retriever.redis_service", redis_svc),
        patch("app.services.memory.refresher.graph_service", graph_svc),
        patch("app.services.memory.refresher.redis_service", redis_svc),
    ):
        await extractor.extract_and_persist(session_id)

        # Verify extraction
        # Note: extraction might place nodes in different categories depending on LLM.
        # We'll check the total knowledge nodes in Neo4j.
        async with graph_svc.driver.session() as session:
            res = await session.run("MATCH (n:Knowledge) RETURN count(n) as count")
            count = await res.single()
            logger.info(f"📊 Extraction complete. Knowledge nodes in Neo4j: {count['count']}")
            assert count["count"] > 0

        logger.info("Waiting 60s to reset Gemini RPM...")
        time.sleep(60)
        # --- ITERATION 2: REDIS/NOSQL ---
        logger.info("🚀 ITERATION 2: Injecting more messages...")
        for msg in batch_2:
            text = msg.get("text")
            if not text:
                continue
            if "Updated room membership" in text:
                continue
            role = "user" if msg["creator"]["user_type"] == "Human" else "assistant"
            content = f"{msg['creator']['name']}: {text}"
            await session_mgr.add_message(session_id, role, content)

        time.sleep(5)
        logger.info("🧠 Running Context Extraction for Batch 2...")
        await extractor.extract_and_persist(session_id)

        time.sleep(5)
        # --- EVOLUTION ---
        logger.info("🔄 Running Graph Evolution (Deduplication & Re-Summarization)...")
        # Ensure some nodes are in the dirty set
        await evolver.evolve()

        # --- RETRIEVAL & RECALL ---
        test_query = "What did Johnny LIN say about using Redis for short-term memory?"
        logger.info(f"💬 Testing Retrieval and LLM Recall for: '{test_query}'")

        # Simulate retrieval
        memory_context = await retriever.get_relevant_context(session_id, test_query)
        logger.info(f"📖 Retrieved Context (excerpt): {memory_context[:300]}...")

        # Johnny LIN mentions Redis in message 5 (index 4 in file)
        assert any(word in memory_context for word in ["Redis", "Memory", "Memorystore", "短期記憶", "NOSQL"])

        # Final Chat Ability Test
        session = await session_mgr.get_session(session_id)
        history = [{"role": m.role, "content": m.content} for m in session.messages[-5:]]

        messages_for_llm = [
            {
                "role": "system",
                "content": f"You are a helpful assistant. Use the following memory context to answer correctly: {memory_context}",
            },
            *history,
            {"role": "user", "content": test_query},
        ]

        # Rate limit protection
        logger.info("Waiting 30s before final recall test...")
        time.sleep(30)
        response = await invoke_llm(messages=messages_for_llm)
        logger.info(f"🤖 LLM Response: {response}")

        assert any(
            word.lower() in response.lower()
            for word in ["Redis", "Memory", "Memorystore", "短期記憶", "NOSQL", "google sheet"]
        )

    # Cleanup
    await graph_svc.close()
    await redis_svc.close()
    logger.info("✅ Integration Test Passed!")


if __name__ == "__main__":
    print("Please run this test using: uv run pytest tests/test_end_to_end_it.py")
