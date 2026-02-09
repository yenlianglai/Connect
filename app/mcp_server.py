"""
MCP Server for Connect - Exposes knowledge graph capabilities to Cursor IDE.

Tools:
- quick_record: Record and extract insights into the knowledge graph
- retrieve_knowledge: Search the knowledge graph for relevant context
"""

import logging
import sys
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.core.config import settings
from app.core.session.manager import session_manager
from app.services.extractor import context_extractor
from app.services.memory.retriever import memory_retriever

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

SESSION_ID_PREFIX_QUICK = "mcp_quick_"
SESSION_ID_PREFIX_SEARCH = "mcp_search_"
QUICK_INSIGHT_TOPIC_NAME = "Cursor Quick Insight"
QUICK_INSIGHT_SOURCE = "cursor_mcp_quick"
SESSION_ID_SUFFIX_LENGTH = 8

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------


def _configure_logging() -> Path:
    """Configure MCP logging to file and stderr. Returns path to log file."""
    log_path = Path(__file__).parent.parent / "logs" / "mcp_server.log"
    log_path.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stderr),
        ],
    )
    return log_path


LOG_FILE = _configure_logging()
logger = logging.getLogger(__name__)
logger.info("🔌 MCP Server starting...")


# -----------------------------------------------------------------------------
# MCP Server
# -----------------------------------------------------------------------------

mcp = FastMCP(
    "connect",
    instructions="""
    Connect is a knowledge graph system that records and organizes your learning.

    Tools:
    - quick_record: Record and extract a single insight directly into the knowledge graph
    - retrieve_knowledge: Search your knowledge graph for relevant context
    """,
)


# -----------------------------------------------------------------------------
# MCP Tools
# -----------------------------------------------------------------------------


def _make_temp_session_id(prefix: str) -> str:
    """Generate a unique temporary session ID for MCP operations."""
    return f"{prefix}{uuid.uuid4().hex[:SESSION_ID_SUFFIX_LENGTH]}"


@mcp.tool()
async def quick_record(insight: str, category: str = "") -> str:
    """
    Record pre-summarized knowledge and let the extractor categorize it.

    IMPORTANT: The Cursor AI should summarize/extract the core insight first as an
    insightful document (coherent paragraph with context, idea, and takeaway—not a
    single sentence or fragment). This tool then lets the extractor:
    - Navigate taxonomy to find the best category
    - Create semantic relationships with related concepts
    - Generate proper descriptions and tags

    Args:
        insight: Pre-filtered, insightful document from Cursor AI (context + key idea + why it matters)
        category: Optional natural language category hint (e.g., "React", "software engineering", "business")

    Returns:
        Confirmation that extraction started
    """
    logger.info(
        "quick_record called | category=%r | insight_len=%d",
        category,
        len(insight),
    )
    session_id = _make_temp_session_id(SESSION_ID_PREFIX_QUICK)

    await session_manager.create_session(
        session_id,
        metadata={
            "topic_name": QUICK_INSIGHT_TOPIC_NAME,
            "source": QUICK_INSIGHT_SOURCE,
        },
    )
    await session_manager.add_message(session_id, "user", insight)
    logger.info("Created temporary session: %s", session_id)

    category_hint = category.strip() or None
    try:
        logger.info("Starting extraction | category_hint=%s", category_hint)
        await context_extractor.extract_and_persist(session_id, category_hint=category_hint)
        category_info = f"with hint '{category}'" if category_hint else "pure content-based"
        logger.info("Extraction completed %s", category_info)
        return (
            "Insight recorded successfully!\n\n"
            f"The extractor processed ({category_info}):\n"
            "- Finding optimal category in taxonomy\n"
            "- Creating semantic relationships\n"
            "- Generating tags and descriptions\n\n"
            "You can now search for it."
        )
    except Exception as e:
        logger.error("Error in quick_record: %s", e, exc_info=True)
        return f"Error processing insight: {str(e)}"


@mcp.tool()
async def retrieve_knowledge(query: str) -> str:
    """
    Search Connect's knowledge graph for relevant information.

    Args:
        query: Natural language search query

    Returns:
        Relevant knowledge from the graph
    """
    query_preview = query[:100] + "..." if len(query) > 100 else query
    logger.info("retrieve_knowledge called | query=%r", query_preview)
    session_id = _make_temp_session_id(SESSION_ID_PREFIX_SEARCH)

    try:
        context, retrieved_ids = await memory_retriever.get_relevant_context(session_id, query)
    except Exception as e:
        logger.error("Error in retrieve_knowledge: %s", e, exc_info=True)
        return f"Error searching knowledge graph: {str(e)}"

    if not context or not context.strip():
        logger.info("No relevant knowledge found for query")
        return "No relevant knowledge found."

    result_count = len(retrieved_ids) if retrieved_ids else 0
    logger.info("Found %d relevant items", result_count)
    return f"Found {result_count} relevant items:\n\n{context}"


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server. Transport from MCP_TRANSPORT env (default: stdio)."""
    transport = settings.MCP_TRANSPORT or "stdio"
    logger.info("Starting MCP server | transport=%s | log_file=%s", transport, LOG_FILE)

    if transport == "streamable-http":
        host = settings.MCP_HOST
        port = settings.MCP_PORT
        logger.info("Connect MCP HTTP at http://%s:%s/mcp", host, port)
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
