import json
import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """
    Service for interacting with Redis, managing session context and hot knowledge pointers.
    """

    def __init__(self, url: str | None = None):
        self.url = url or settings.REDIS_URL
        self._redis: redis.Redis | None = None

    async def get_client(self) -> redis.Redis:
        """Lazily initializes and returns the Redis client."""
        if self._redis is None:
            self._redis = redis.from_url(self.url, decode_responses=True)
        return self._redis

    async def close(self):
        """Closes the Redis connection."""
        if self._redis:
            await self._redis.close()

    # --- Session Context (Working Memory) ---

    async def get_session_context(self, session_id: str) -> dict | None:
        """Fetch the current conversation summary and state from Redis."""
        client = await self.get_client()
        data = await client.get(f"session:{session_id}:context")
        return json.loads(data) if data else None

    async def set_session_context(self, session_id: str, context: dict, expire: int = 3600):
        """Update the conversation summary and state in Redis."""
        client = await self.get_client()
        await client.set(f"session:{session_id}:context", json.dumps(context), ex=expire)

    # --- Active Knowledge Pointers (using ZSET for LRU pruning) ---

    async def get_active_node_ids(self, session_id: str, limit: int = 20) -> list[str]:
        """Get IDs of knowledge nodes currently marked as 'hot', ordered by recent usage."""
        client = await self.get_client()
        # Returns nodes from most recent to oldest (descending score)
        return await client.zrevrange(f"session:{session_id}:active_nodes", 0, limit - 1)

    async def add_active_node_id(self, session_id: str, node_id: str, score: float, expire: int = 3600):
        """Mark a knowledge node as 'hot' with a score (timestamp) for LRU tracking."""
        client = await self.get_client()
        key = f"session:{session_id}:active_nodes"
        await client.zadd(key, {node_id: score})
        await client.expire(key, expire)

    async def prune_active_nodes(self, session_id: str, max_nodes: int):
        """Prune oldest nodes if the set exceeds max_nodes."""
        client = await self.get_client()
        key = f"session:{session_id}:active_nodes"
        count = await client.zcard(key)
        if count > max_nodes:
            await client.zremrangebyrank(key, 0, count - max_nodes - 1)
            logger.debug(f"Pruned {count - max_nodes} oldest nodes for session {session_id}")

    # --- Global Knowledge Cache (Summarized Nodes) ---

    async def get_knowledge_nodes(self, node_ids: list[str]) -> list[dict]:
        """Batch fetch summarized knowledge nodes from global cache."""
        if not node_ids:
            return []
        client = await self.get_client()
        keys = [f"knowledge:{nid}" for nid in node_ids]
        results = await client.mget(keys)
        return [json.loads(r) for r in results if r]

    async def set_knowledge_node(self, node_id: str, data: dict, expire: int = 86400):
        """Cache a summarized knowledge node in global cache (default 24h)."""
        client = await self.get_client()
        await client.set(f"knowledge:{node_id}", json.dumps(data), ex=expire)

    # --- Extraction Cursor Tracking ---

    async def get_extraction_cursor(self, session_id: str) -> str | None:
        """Fetch the timestamp of the last message processed for extraction."""
        client = await self.get_client()
        return await client.get(f"session:{session_id}:extraction_cursor")

    async def set_extraction_cursor(self, session_id: str, timestamp: str):
        """Update the timestamp of the last message processed for extraction."""
        client = await self.get_client()
        await client.set(f"session:{session_id}:extraction_cursor", timestamp)


# Singleton instance
redis_service = RedisService()
