#!/usr/bin/env python3
"""
Restore graph to a clean state and inject the FastAPI test session for extraction testing.

1. Wipes Neo4j graph and re-seeds the base taxonomy.
2. Deletes the test session if it exists, recreates it with conversation messages,
   and resets the extraction cursor so Extract will process all messages.

Run: uv run python scripts/restore_graph_and_seed_test_session.py
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.session.manager import session_manager
from app.services.graph.neo4j_service import graph_service
from app.services.memory.redis_service import redis_service
from scripts.seed_fastapi_learning_session import CONVERSATION, SESSION_ID, TOPIC_NAME
from scripts.seed_taxonomy import seed_taxonomy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    # 1. Wipe graph and re-seed taxonomy
    logger.info("🧹 Restoring graph state (wipe + re-seed taxonomy)...")
    async with graph_service.driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        logger.info("🗑️  All nodes and relationships deleted.")
    await seed_taxonomy()
    await graph_service.close()
    logger.info("✨ Graph reset to initial seeded state.")

    # 2. Re-inject test session: delete if exists, create, add messages, reset cursor
    logger.info("📥 Injecting test session: %s (%s)", SESSION_ID, TOPIC_NAME)
    await session_manager.delete_session(SESSION_ID)

    await session_manager.create_session(
        SESSION_ID,
        metadata={"topic_name": TOPIC_NAME, "source": "restore_script"},
    )
    for role, content in CONVERSATION:
        ts = datetime.now(UTC)
        await session_manager.add_message(SESSION_ID, role, content, timestamp=ts)
        logger.info("  Added %s: %s...", role, content[:50])
    await redis_service.set_extraction_cursor(SESSION_ID, "")
    logger.info("Done. Session has %d messages. Extraction cursor reset.", len(CONVERSATION))
    logger.info("  In the app: select this session and click Extract to run extraction.")


if __name__ == "__main__":
    asyncio.run(main())
