import json
import logging
import time
from typing import Any

from app.prompts.memory import KNOWLEDGE_CONTEXT_TEMPLATE
from app.services.graph.neo4j_service import GraphService, graph_service
from app.services.memory.redis_service import RedisService, redis_service

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    Retrieves relevant knowledge from hot memory (Redis) and long-term memory (Neo4j)
    to enhance chat prompts with contextual information.
    """

    def __init__(self, redis_svc: RedisService | None = None, graph_svc: GraphService | None = None):
        self.redis = redis_svc or redis_service
        self.graph = graph_svc or graph_service

    async def get_relevant_context(
        self, session_id: str, query: str, category_ids: list[str] | None = None
    ) -> tuple[str, list[str]]:
        """
        Retrieves relevant context for a query by combining hot memory and graph search.

        Args:
            session_id: The session identifier
            query: The user's query text
            category_ids: Optional list of category IDs to scope search (None = entire graph)

        Returns:
            Tuple of (formatted_context_string, list_of_retrieved_node_ids)
        """
        try:
            # Step 1: Fetch hot memory from Redis
            hot_nodes, hot_node_ids = await self._fetch_hot_memory(session_id)

            # Step 2: Search graph for additional relevant nodes (with optional category scoping)
            new_nodes = await self._search_graph(query, category_ids=category_ids)

            # Step 3: Merge and cache results
            all_nodes, retrieved_ids = await self._merge_and_cache(session_id, hot_nodes, hot_node_ids, new_nodes)

            # Step 4: Format context for LLM
            context = self._format_context(all_nodes)

            return context, retrieved_ids

        except Exception as e:
            logger.error(f"Failed to retrieve context for session {session_id}: {e}", exc_info=True)
            return "No specific memory context found for this query.", []

    async def _fetch_hot_memory(self, session_id: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Fetches hot memory nodes from Redis."""
        try:
            active_ids = await self.redis.get_active_node_ids(session_id)
            if not active_ids:
                return [], []

            hot_nodes = await self.redis.get_knowledge_nodes(active_ids)
            logger.debug(f"Retrieved {len(hot_nodes)} hot nodes from Redis for session {session_id}")

            return hot_nodes, active_ids
        except Exception as e:
            logger.warning(f"Failed to fetch hot memory for session {session_id}: {e}")
            return [], []

    async def _search_graph(self, query: str, limit: int = 5, category_ids: list[str] | None = None) -> list[Any]:
        """
        Searches the knowledge graph for relevant nodes.

        Args:
            query: Search query text
            limit: Maximum number of results
            category_ids: Optional list of category IDs to scope search (None = entire graph)
        """
        try:
            # If multiple categories specified, search each subtree and combine results
            if category_ids and len(category_ids) > 0:
                all_nodes = []
                seen_ids = set()
                # Search each category subtree
                for cat_id in category_ids:
                    nodes = await self.graph.graph_rag_search(query_text=query, category_id=cat_id, limit=limit)
                    for node in nodes:
                        if node.id not in seen_ids:
                            all_nodes.append(node)
                            seen_ids.add(node.id)
                # Limit total results
                nodes = all_nodes[:limit]
            else:
                # Search entire graph
                nodes = await self.graph.graph_rag_search(query_text=query, limit=limit)

            logger.debug(f"Graph search returned {len(nodes)} nodes for query: {query[:50]}...")
            return nodes
        except Exception as e:
            logger.warning(f"Graph search failed for query '{query[:50]}...': {e}")
            return []

    async def _merge_and_cache(
        self, session_id: str, hot_nodes: list[dict[str, Any]], hot_node_ids: list[str], new_nodes: list[Any]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Merges hot memory and graph search results, avoiding duplicates.
        Caches new nodes to Redis using batched operations.
        """
        if not hot_nodes and not new_nodes:
            return [], []

        # Track seen nodes and prepare for batch caching
        seen_ids = {node["id"] for node in hot_nodes}
        retrieved_ids = list(hot_node_ids)  # Start with hot node IDs for UI highlighting
        nodes_to_cache = []
        nodes_to_update_score = []
        now = time.time()

        # Process new nodes from graph search
        for node in new_nodes:
            if node.id in seen_ids:
                # Node already in hot memory - just update score
                nodes_to_update_score.append((session_id, node.id, now))
                if node.id not in retrieved_ids:
                    retrieved_ids.append(node.id)
            else:
                # New node - prepare for caching
                node_data = {
                    "id": node.id,
                    "tags": node.tags,
                    "description": node.description,
                    "content": node.content,
                }
                hot_nodes.append(node_data)
                nodes_to_cache.append((node.id, node_data))
                retrieved_ids.append(node.id)
                seen_ids.add(node.id)

        # Batch cache operations
        await self._batch_cache_nodes(session_id, nodes_to_cache, nodes_to_update_score)

        return hot_nodes, retrieved_ids

    async def _batch_cache_nodes(
        self,
        session_id: str,
        nodes_to_cache: list[tuple[str, dict[str, Any]]],
        nodes_to_update_score: list[tuple[str, str, float]],
    ):
        """
        Batches Redis operations for efficiency using pipeline.

        If caching fails, the system continues normally - nodes will be retrieved
        from Neo4j on the next query. Caching is an optimization, not critical.
        """
        if not nodes_to_cache and not nodes_to_update_score:
            return

        try:
            client = await self.redis.get_client()

            # Use async redis pipeline for batched writes
            pipe = client.pipeline()

            # Cache new nodes
            for node_id, node_data in nodes_to_cache:
                pipe.set(
                    f"knowledge:{node_id}",
                    json.dumps(node_data),
                    ex=86400,  # 24 hours
                )

            # Update scores for existing nodes
            for sess_id, node_id, score in nodes_to_update_score:
                pipe.zadd(f"session:{sess_id}:active_nodes", {node_id: score})
                pipe.expire(f"session:{sess_id}:active_nodes", 3600)

            await pipe.execute()
            logger.debug(f"Cached {len(nodes_to_cache)} new nodes and updated {len(nodes_to_update_score)} scores")

        except Exception as e:
            # Log warning but continue - caching is non-critical
            # Nodes will be retrieved from Neo4j on next query anyway
            logger.warning(f"Failed to cache nodes to Redis (non-critical): {e}")

    def _format_context(self, nodes: list[dict[str, Any]]) -> str:
        """Formats nodes into a context string for the LLM prompt."""
        if not nodes:
            return "No specific memory context found for this query."

        context_parts = []
        for node in nodes:
            try:
                context_parts.append(
                    KNOWLEDGE_CONTEXT_TEMPLATE.format(
                        tags=", ".join(node.get("tags", [])),
                        description=node.get("description", "No description"),
                        content=node.get("content", ""),
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to format node {node.get('id', 'unknown')}: {e}")
                continue

        return "\n".join(context_parts)


# Singleton instance
memory_retriever = MemoryRetriever()
