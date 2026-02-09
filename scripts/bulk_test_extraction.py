import asyncio
import json
import logging
import re
from datetime import UTC, datetime

from app.core.session.manager import session_manager
from app.services.evolver import memory_evolver
from app.services.extractor import context_extractor
from app.services.memory.redis_service import redis_service

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SESSION_ID = "bulk-test-2024"


def parse_chinese_date(date_str):
    """
    Parses date format like: "2024年1月22日 星期一上午9:33:45 [UTC]"
    """
    try:
        # Extract year, month, day, period (上午/下午/凌晨), hour, min, sec
        match = re.search(r"(\d+)年(\d+)月(\d+)日.*?([上下]午|凌晨)(\d+):(\d+):(\d+)", date_str)
        if not match:
            return None

        y, m, d, period, hh, mm, ss = match.groups()
        y, m, d, hh, mm, ss = map(int, [y, m, d, hh, mm, ss])

        # Handle 12-hour format for PM
        if period == "下午" and hh < 12:
            hh += 12
        elif (period == "上午" or period == "凌晨") and hh == 12:
            hh = 0

        return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)
    except Exception as e:
        logger.error(f"Error parsing date {date_str}: {e}")
        return None


async def run_bulk_test():
    logger.info("Starting Bulk Test for Connect Hierarchical Memory...")

    # 1. Load messages
    with open("tests/data/messages.json", encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])
    logger.info(f"Loaded {len(messages)} messages.")

    # 2. Parse and Sort
    parsed_messages = []
    for msg in messages:
        if "created_date" not in msg or "text" not in msg:
            continue

        ts = parse_chinese_date(msg["created_date"])
        if ts:
            role = "user"
            if msg.get("creator", {}).get("user_type") != "Human":
                role = "assistant"

            parsed_messages.append({"role": role, "content": msg["text"], "timestamp": ts})

    parsed_messages.sort(key=lambda x: x["timestamp"])
    logger.info(f"Sorted {len(parsed_messages)} valid messages.")

    # 3. Process in batches to simulate incremental growth
    # We'll do batches of 30 messages at a time to trigger multiple extractions
    BATCH_SIZE = 30
    total_messages = len(parsed_messages)

    # Clear existing session data for clean test
    await session_manager.delete_session(SESSION_ID)
    await redis_service.set_extraction_cursor(SESSION_ID, "")  # Reset cursor

    logger.info(f"Processing in batches of {BATCH_SIZE}...")

    for i in range(0, total_messages, BATCH_SIZE):
        batch = parsed_messages[i : i + BATCH_SIZE]
        logger.info(f"\n--- [Batch {i // BATCH_SIZE + 1}] Processing {len(batch)} messages ---")

        # Insert batch into MongoDB
        for msg in batch:
            await session_manager.add_message(
                session_id=SESSION_ID, role=msg["role"], content=msg["content"], timestamp=msg["timestamp"]
            )

        # Trigger Extraction
        logger.info("Triggering Context Extraction...")
        await context_extractor.extract_and_persist(SESSION_ID)

        # Rate limit protection (Gemini 2.0 Flash Lite/Lite has limits)
        logger.info("Sleeping 5s for rate limit...")
        await asyncio.sleep(5)

        # Every 2 batches, trigger evolution
        if (i // BATCH_SIZE + 1) % 2 == 0:
            logger.info("Triggering Graph Evolution...")
            await memory_evolver.evolve()
            logger.info("Sleeping 5s after evolution...")
            await asyncio.sleep(5)

    logger.info("\n✅ Bulk test completed!")
    logger.info(f"Data stored in session: {SESSION_ID}")
    logger.info("You can now view the results in the Neo4j Browser or the Frontend UI.")


if __name__ == "__main__":
    asyncio.run(run_bulk_test())
