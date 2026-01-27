import logging
import sys

from app.core.config import settings


def setup_logging():
    # Configure the root logger
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,  # Force override if already configured
    )

    # Set levels for specific libraries
    logging.getLogger("neo4j").setLevel(logging.ERROR)  # Suppress schema warnings
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("neo4j_graphrag").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"🚀 Logging initialized with level: {settings.LOG_LEVEL}")
