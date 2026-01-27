import logging
import time

from app.services.graph.neo4j_service import GraphService, graph_service
from app.services.memory.redis_service import RedisService, redis_service

logger = logging.getLogger(__name__)


class MemoryRefresher:
    """
    Service responsible for proactively pre-fetching knowledge from Neo4j
    to warm up the Redis hot memory based on the current session context.
    """

    def __init__(
        self, redis_svc: RedisService | None = None, graph_svc: GraphService | None = None, max_active_nodes: int = 10
    ):
        self.redis = redis_svc or redis_service
        self.graph = graph_svc or graph_service
        self.max_active_nodes = max_active_nodes

    async def refresh_hot_memory(self, session_id: str):
        """
        Fetches neighbors of active nodes and caches them in Redis.
        Also performs LRU pruning to maintain cache size.
        """
        logger.info(f"🔄 Refreshing hot memory for session: {session_id}")

        # 1. Get current active nodes from Redis (using ZSET)
        active_ids = await self.redis.get_active_node_ids(session_id)

        if not active_ids:
            logger.debug("No active nodes to refresh.")
            return

        # 2. Find their structural neighbors in Neo4j
        neighbors = await self.graph.get_neighbor_nodes(active_ids, limit=5)

        # 3. Cache neighbors in Redis and mark them as active
        now = time.time()
        for neighbor in neighbors:
            node_data = {
                "id": neighbor.id,
                "tags": neighbor.tags,
                "description": neighbor.description,
                "content": neighbor.content,
            }
            # Cache the summarized fact
            await self.redis.set_knowledge_node(neighbor.id, node_data)
            # Add to session's active set with a slightly older timestamp to prioritize current topic
            await self.redis.add_active_node_id(session_id, neighbor.id, score=now - 1)

        # 4. Prune Active Nodes (True LRU using ZSET)
        await self.redis.prune_active_nodes(session_id, self.max_active_nodes)

        logger.info("✅ Hot memory refreshed.")


# Singleton instance
memory_refresher = MemoryRefresher()
