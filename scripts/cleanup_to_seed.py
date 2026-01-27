import asyncio
import logging
from app.services.graph.neo4j_service import graph_service
from scripts.seed_taxonomy import seed_taxonomy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup_to_seed():
    """Wipes the entire graph and re-seeds only the base taxonomy."""
    logger.info("🧹 Starting graph cleanup...")
    
    async with graph_service.driver.session() as session:
        # Wipe everything
        await session.run("MATCH (n) DETACH DELETE n")
        logger.info("🗑️  All nodes and relationships deleted.")

    # Re-seed the base taxonomy
    await seed_taxonomy()
    
    await graph_service.close()
    logger.info("✨ Graph reset to initial seeded state.")

if __name__ == "__main__":
    asyncio.run(cleanup_to_seed())

