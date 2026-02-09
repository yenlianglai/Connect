# Standard library imports
import logging
from datetime import UTC, datetime
from typing import Any

# Third-party imports
import httpx
import numpy as np
from google import genai
from google.genai import types
from neo4j import AsyncGraphDatabase, GraphDatabase
from neo4j_graphrag.indexes import create_vector_index
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

# Local imports
from app.core.config import settings
from app.models.nodes import Category, KnowledgeNode, Relationship, VerticalRelationshipType

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """
    Custom embedder using Ollama's embedding models.
    Conforms to the interface expected by neo4j-graphrag.
    """

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION

    def embed_query(self, text: str) -> list[float]:
        """Embed a single string and return normalized vector."""
        # Handle empty or whitespace-only strings
        if not text or not text.strip():
            logger.warning("Empty text provided to embedder, returning zero vector")
            return [0.0] * self.dimension

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text.strip(),  # Strip whitespace
                    },
                )
                response.raise_for_status()
                result = response.json()

                # Extract embedding vector
                embedding_values = result.get("embedding", [])
                if not embedding_values:
                    logger.error(f"Empty embedding returned from Ollama for text: {text[:100]}...")
                    raise ValueError("Empty embedding returned from Ollama")

                embedding_np = np.array(embedding_values)

                # Normalize the vector
                norm = np.linalg.norm(embedding_np)
                if norm > 0:
                    embedding_np = embedding_np / norm

                # If dimension doesn't match, pad or truncate
                if len(embedding_np) != self.dimension:
                    if len(embedding_np) < self.dimension:
                        # Pad with zeros
                        padding = np.zeros(self.dimension - len(embedding_np))
                        embedding_np = np.concatenate([embedding_np, padding])
                    else:
                        # Truncate
                        embedding_np = embedding_np[: self.dimension]

                return embedding_np.tolist()
        except Exception as e:
            logger.error(f"Ollama embedding failed: {e}")
            raise


class GeminiEmbedder:
    """
    Custom embedder using Gemini's gemini-embedding-001.
    Conforms to the interface expected by neo4j-graphrag.
    """

    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.GEMINI_EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION

    def embed_query(self, text: str) -> list[float]:
        """Embed a single string and return normalized vector."""
        result = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dimension),
        )

        embedding_values = result.embeddings[0].values
        embedding_np = np.array(embedding_values)
        norm = np.linalg.norm(embedding_np)
        if norm > 0:
            embedding_np = embedding_np / norm

        return embedding_np.tolist()


def node_result_formatter(record: Any) -> RetrieverResultItem:
    """Custom formatter for VectorCypherRetriever to preserve raw record data in metadata."""
    return RetrieverResultItem(
        content=str(record),
        metadata={
            "node": dict(record["node"]) if record.get("node") else None,
            "neighbor": dict(record["neighbor"]) if record.get("neighbor") else None,
        },
    )


class GraphService:
    """
    Service for interacting with Neo4j graph database.
    Provides general graph operations: node CRUD, relationships, and vector search.
    """

    # Constants for node labels and relationship types
    LABEL_KNOWLEDGE = "Knowledge"
    LABEL_CATEGORY = "Category"
    LABEL_SESSION = "Session"

    INDEX_KNOWLEDGE = "knowledge_vector_index"
    INDEX_CATEGORY = "category_vector_index"

    REL_BELONGS_TO = "BELONGS_TO"
    REL_SUB_CATEGORY_OF = "SUB_CATEGORY_OF"
    REL_RELATED = "RELATED"

    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        auth = (user or settings.NEO4J_USER, password or settings.NEO4J_PASSWORD)
        url = uri or settings.NEO4J_URI
        self.driver = AsyncGraphDatabase.driver(url, auth=auth)
        self.sync_driver = GraphDatabase.driver(url, auth=auth)

        # Select embedder based on LLM_PROVIDER
        if settings.LLM_PROVIDER == "ollama":
            self.embedder = OllamaEmbedder()
            logger.info(f"Using Ollama embedder with model: {settings.OLLAMA_EMBEDDING_MODEL}")
        else:
            self.embedder = GeminiEmbedder()
            logger.info(f"Using Gemini embedder with model: {settings.GEMINI_EMBEDDING_MODEL}")

    async def close(self):
        """Closes the Neo4j driver connections."""
        await self.driver.close()
        self.sync_driver.close()

    async def ensure_vector_index(self):
        """Ensures vector indexes exist for Knowledge and Category nodes."""
        try:
            for label, index_name in [
                (self.LABEL_KNOWLEDGE, self.INDEX_KNOWLEDGE),
                (self.LABEL_CATEGORY, self.INDEX_CATEGORY),
            ]:
                create_vector_index(
                    self.sync_driver,
                    name=index_name,
                    label=label,
                    embedding_property="embedding",
                    dimensions=settings.EMBEDDING_DIMENSION,
                    similarity_fn="cosine",
                )
            logger.info("✅ Neo4j Vector Indexes ensured.")
        except Exception as e:
            logger.debug(f"Vector index status: {e}")

    # ========== Node Creation ==========

    async def create_knowledge_node(self, node: KnowledgeNode):
        """Creates or updates a Knowledge node with its vector embedding."""
        embedding = self.embedder.embed_query(node.content)
        await self._create_node(
            label=self.LABEL_KNOWLEDGE,
            node_id=node.id,
            properties={
                "session_id": node.session_id,
                "tags": node.tags,
                "description": node.description,
                "content": node.content,
                "worth_of_learning": node.worth_of_learning,
                "embedding": embedding,
            },
            timestamps={"created_at": node.created_at, "updated_at": node.updated_at},
        )

    async def create_category_node(self, category: Category):
        """Creates or updates a Category node with its vector embedding."""
        embedding = self.embedder.embed_query(f"{category.name} {category.summary}")
        await self._create_node(
            label=self.LABEL_CATEGORY,
            node_id=category.id,
            properties={
                "name": category.name,
                "summary": category.summary,
                "level": category.level,
                "insert_counter": category.insert_counter,
                "embedding": embedding,
            },
            timestamps={"created_at": category.created_at, "updated_at": category.updated_at},
        )

    async def _create_node(
        self,
        label: str,
        node_id: str,
        properties: dict[str, Any],
        timestamps: dict[str, datetime],
    ):
        """General node creation/update helper."""

        async def _create(tx):
            set_clauses = []
            params = {"id": node_id}

            # Build SET clauses for properties
            for key, value in properties.items():
                if value is not None:
                    set_clauses.append(f"node.{key} = ${key}")
                    params[key] = value

            # Handle timestamps
            for ts_key, ts_value in timestamps.items():
                if ts_value:
                    set_clauses.append(f"node.{ts_key} = datetime(${ts_key})")
                    params[ts_key] = ts_value.isoformat()

            set_str = ", ".join(set_clauses)

            query = (
                f"MERGE (node:{label} {{id: $id}}) "
                f"ON CREATE SET {set_str.replace('node.', 'node.')} "
                f"ON MATCH SET {set_str} "
                "RETURN node"
            )
            await tx.run(query, **params)

        async with self.driver.session() as session:
            await session.execute_write(_create)

    # ========== Graph Search ==========

    async def graph_rag_search(
        self, query_text: str, category_id: str | None = None, limit: int = 5, hops: int = 1
    ) -> list[KnowledgeNode]:
        """
        Performs hybrid Vector + Graph search (GraphRAG) on Knowledge nodes.

        Args:
            query_text: The search query
            category_id: Optional category ID to filter results (None = entire graph)
            limit: Maximum number of results to return
            hops: Graph traversal depth (0 = no traversal, just vector search)

        Returns:
            List of KnowledgeNode objects, sorted by relevance
        """
        try:
            retrieval_query = self._build_retrieval_query(hops, category_id)
            retriever = self._create_retriever(retrieval_query)

            search_result = retriever.search(
                query_text=query_text, top_k=limit, query_params={"category_id": category_id}
            )

            nodes = self._parse_search_results(search_result, hops)
            logger.debug(f"GraphRAG search returned {len(nodes)} nodes")

            return nodes

        except Exception as e:
            logger.error(f"GraphRAG search failed: {e}", exc_info=True)
            return []

    def _build_retrieval_query(self, hops: int, category_id: str | None) -> str:
        """Builds the Cypher retrieval query based on traversal depth and category filter."""
        category_filter = "($category_id IS NULL OR (node)-[:BELONGS_TO]->(:Category {id: $category_id}))"

        if hops > 0:
            return (
                f"OPTIONAL MATCH (node)-[*1..{hops}]-(neighbor) "
                f"WHERE node:{self.LABEL_KNOWLEDGE} "
                f"AND {category_filter} "
                "RETURN DISTINCT node, neighbor"
            )
        else:
            return f"MATCH (node:{self.LABEL_KNOWLEDGE}) WHERE {category_filter} RETURN node"

    def _create_retriever(self, retrieval_query: str) -> VectorCypherRetriever:
        """Creates a VectorCypherRetriever instance with the given query."""
        return VectorCypherRetriever(
            self.sync_driver,
            index_name=self.INDEX_KNOWLEDGE,
            retrieval_query=retrieval_query,
            embedder=self.embedder,
            result_formatter=node_result_formatter,
        )

    def _parse_search_results(self, search_result: Any, hops: int) -> list[KnowledgeNode]:
        """Parses search results into KnowledgeNode objects."""
        nodes_dict = {}
        keys_to_check = ["node", "neighbor"] if hops > 0 else ["node"]

        for item in search_result.items:
            record_data = item.metadata

            for key in keys_to_check:
                node_data = record_data.get(key)

                if not node_data or not isinstance(node_data, dict):
                    continue

                if "id" not in node_data or "content" not in node_data:
                    continue

                node_id = node_data.get("id")
                if node_id and node_id not in nodes_dict:
                    try:
                        self._cleanup_node_data(node_data)
                        nodes_dict[node_id] = KnowledgeNode(**node_data)
                    except Exception as e:
                        logger.warning(f"Failed to parse KnowledgeNode {node_id}: {e}")
                        continue

        return list(nodes_dict.values())

    def _cleanup_node_data(self, node_data: dict):
        """Cleans up Neo4j node data for Pydantic model compatibility."""
        for dt_key in ["created_at", "updated_at"]:
            if dt_key in node_data and hasattr(node_data[dt_key], "to_native"):
                node_data[dt_key] = node_data[dt_key].to_native()
        node_data.pop("embedding", None)

    # ========== Relationships ==========

    async def create_relationship(self, rel: Relationship):
        """Creates a relationship between two nodes."""
        edge_label = self._map_relationship_type_to_label(rel.relationship_type)

        async def _create(tx):
            query = (
                "MATCH (a {id: $source_id}) "
                "MATCH (b {id: $target_id}) "
                f"MERGE (a)-[rel:{edge_label}]->(b) "
                "SET rel.type = $rel_type, "
                "    rel.reasoning = $reasoning, "
                "    rel.confidence = $confidence, "
                "    rel.created_at = datetime($created_at) "
                "RETURN rel"
            )
            await tx.run(
                query,
                source_id=rel.source_id,
                target_id=rel.target_id,
                rel_type=rel.relationship_type.value
                if hasattr(rel.relationship_type, "value")
                else rel.relationship_type,
                reasoning=rel.reasoning,
                confidence=rel.confidence,
                created_at=rel.created_at.isoformat(),
            )

        async with self.driver.session() as session:
            await session.execute_write(_create)

    def _map_relationship_type_to_label(self, rel_type: Any) -> str:
        """Maps relationship type enum to Neo4j edge label."""
        if isinstance(rel_type, VerticalRelationshipType):
            if rel_type == VerticalRelationshipType.SUB_CATEGORY_OF:
                return self.REL_SUB_CATEGORY_OF
            elif rel_type == VerticalRelationshipType.BELONGS_TO:
                return self.REL_BELONGS_TO
        return self.REL_RELATED

    async def create_manual_link(self, source_id: str, target_id: str, rel_type: str):
        """Creates a manual relationship between two nodes."""

        async def _create(tx):
            query = f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) MERGE (a)-[r:{rel_type}]->(b) RETURN r"
            await tx.run(query, source_id=source_id, target_id=target_id)

        async with self.driver.session() as session:
            await session.execute_write(_create)

    async def delete_manual_link(self, source_id: str, target_id: str, rel_type: str):
        """Removes a specific relationship between two nodes."""

        async def _delete(tx):
            query = f"MATCH (a {{id: $source_id}})-[r:{rel_type}]-(b {{id: $target_id}}) DELETE r"
            await tx.run(query, source_id=source_id, target_id=target_id)

        async with self.driver.session() as session:
            await session.execute_write(_delete)

    async def get_relationships(self, node_id: str) -> list[dict[str, Any]]:
        """Retrieves all outgoing relationships for a specific node."""

        async def _get(tx):
            query = (
                "MATCH (n {id: $id})-[r]->(target) "
                "RETURN type(r) as edge_label, r.type as relationship_type, "
                "       r.reasoning as reasoning, target.id as target_id"
            )
            result = await tx.run(query, id=node_id)
            return [
                {
                    "edge_label": record["edge_label"],
                    "relationship_type": record["relationship_type"],
                    "reasoning": record["reasoning"],
                    "target_id": record["target_id"],
                }
                async for record in result
            ]

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    # ========== Node Queries ==========

    async def get_nodes_by_label(self, label: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        General method to retrieve nodes by label with optional filters.

        Args:
            label: Node label (e.g., "Knowledge", "Category")
            filters: Optional dict of property filters (e.g., {"session_id": "abc"})

        Returns:
            List of node dictionaries
        """

        async def _get(tx):
            where_clauses = []
            params = {}

            if filters:
                for key, value in filters.items():
                    where_clauses.append(f"n.{key} = ${key}")
                    params[key] = value

            where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"MATCH (n:{label}) {where_str} RETURN n"
            result = await tx.run(query, **params)

            nodes = []
            async for record in result:
                node_data = dict(record["n"])
                self._cleanup_node_data(node_data)
                nodes.append(node_data)
            return nodes

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    async def get_nodes_by_session(self, session_id: str) -> list[KnowledgeNode]:
        """Retrieves all Knowledge nodes from a specific session."""
        nodes_data = await self.get_nodes_by_label(self.LABEL_KNOWLEDGE, filters={"session_id": session_id})
        return [KnowledgeNode(**data) for data in nodes_data]

    async def get_category_nodes(self, category_id: str) -> list[KnowledgeNode]:
        """Retrieves all Knowledge nodes belonging to a specific category."""

        async def _get(tx):
            query = (
                f"MATCH (n:{self.LABEL_KNOWLEDGE})-[:{self.REL_BELONGS_TO}]->"
                f"(:{self.LABEL_CATEGORY} {{id: $id}}) "
                "RETURN n"
            )
            result = await tx.run(query, id=category_id)
            nodes = []
            async for record in result:
                node_data = dict(record["n"])
                self._cleanup_node_data(node_data)
                nodes.append(KnowledgeNode(**node_data))
            return nodes

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    async def get_sub_categories(self, parent_id: str) -> list[Category]:
        """Retrieves direct sub-categories of a parent category."""

        async def _get(tx):
            query = (
                f"MATCH (c:{self.LABEL_CATEGORY})-[:{self.REL_SUB_CATEGORY_OF}]->"
                f"(:{self.LABEL_CATEGORY} {{id: $id}}) "
                "RETURN c"
            )
            result = await tx.run(query, id=parent_id)
            cats = []
            async for record in result:
                cat_data = dict(record["c"])
                self._cleanup_node_data(cat_data)
                cats.append(Category(**cat_data))
            return cats

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    async def get_neighbor_nodes(self, node_ids: list[str], limit: int = 5) -> list[KnowledgeNode]:
        """Retrieves neighbor Knowledge nodes for a set of node IDs."""
        if not node_ids:
            return []

        async def _get(tx, node_ids, limit):
            query = (
                f"MATCH (n:{self.LABEL_KNOWLEDGE})-[:{self.REL_RELATED}]-(neighbor:{self.LABEL_KNOWLEDGE}) "
                "WHERE n.id IN $node_ids AND NOT neighbor.id IN $node_ids "
                "RETURN DISTINCT neighbor "
                "LIMIT $limit"
            )
            result = await tx.run(query, node_ids=node_ids, limit=limit)
            nodes = []
            async for record in result:
                node_data = dict(record["neighbor"])
                self._cleanup_node_data(node_data)
                nodes.append(KnowledgeNode(**node_data))
            return nodes

        async with self.driver.session() as session:
            return await session.execute_read(_get, node_ids, limit)

    async def get_node_category(self, node_id: str) -> str | None:
        """Finds the category ID a Knowledge node belongs to."""

        async def _get(tx):
            query = (
                f"MATCH (k:{self.LABEL_KNOWLEDGE} {{id: $nid}})-[:{self.REL_BELONGS_TO}]->(c:{self.LABEL_CATEGORY}) "
                "RETURN c.id as category_id"
            )
            result = await tx.run(query, nid=node_id)
            record = await result.single()
            return record["category_id"] if record else None

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    async def get_node_parent(self, category_id: str) -> str | None:
        """Finds the parent category ID for a given category."""

        async def _get(tx):
            query = (
                f"MATCH (c:{self.LABEL_CATEGORY} {{id: $cid}})-[:{self.REL_SUB_CATEGORY_OF}]->(p:{self.LABEL_CATEGORY}) "
                "RETURN p.id as parent_id"
            )
            result = await tx.run(query, cid=category_id)
            record = await result.single()
            return record["parent_id"] if record else None

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    # ========== Node Updates ==========

    async def update_node_properties(self, node_id: str, label: str, properties: dict[str, Any]):
        """
        General method to update node properties.

        Args:
            node_id: The node ID
            label: Node label (e.g., "Knowledge", "Category")
            properties: Dict of properties to update
        """

        async def _update(tx):
            set_clauses = []
            params = {"id": node_id, "now": datetime.now(UTC).isoformat()}

            for key, value in properties.items():
                if value is not None:
                    set_clauses.append(f"n.{key} = ${key}")
                    params[key] = value

            set_clauses.append("n.updated_at = datetime($now)")
            set_str = ", ".join(set_clauses)

            query = f"MATCH (n:{label} {{id: $id}}) SET {set_str}"
            await tx.run(query, **params)

        async with self.driver.session() as session:
            await session.execute_write(_update)

    async def update_knowledge_content(
        self, node_id: str, content: str, description: str | None = None, tags: list[str] | None = None
    ):
        """Updates knowledge node content, description, tags, and re-embeds."""
        properties = {"content": content}
        if description is not None:
            properties["description"] = description
        if tags is not None:
            properties["tags"] = tags

        # Update properties and embedding in a single transaction
        async def _update(tx):
            # Update properties
            set_clauses = ["n.updated_at = datetime($now)"]
            params = {"id": node_id, "now": datetime.now(UTC).isoformat()}

            for key, value in properties.items():
                set_clauses.append(f"n.{key} = ${key}")
                params[key] = value

            set_str = ", ".join(set_clauses)
            await tx.run(f"MATCH (n:{self.LABEL_KNOWLEDGE} {{id: $id}}) SET {set_str}", **params)

            # Re-embed
            try:
                embedding = self.embedder.embed_query(content)
                await tx.run(
                    f"MATCH (n:{self.LABEL_KNOWLEDGE} {{id: $id}}) SET n.embedding = $embedding",
                    id=node_id,
                    embedding=embedding,
                )
            except Exception as e:
                logger.error(f"Failed to update embedding: {e}")

        async with self.driver.session() as session:
            await session.execute_write(_update)

    async def update_category_properties(self, category_id: str, name: str | None = None, summary: str | None = None):
        """Updates category node name and/or summary."""
        properties = {}
        if name is not None:
            properties["name"] = name
        if summary is not None:
            properties["summary"] = summary

        if properties:
            await self.update_node_properties(category_id, self.LABEL_CATEGORY, properties)

    # ========== Category Operations ==========

    async def increment_category_counter(self, category_id: str) -> int:
        """Increments the insert_counter for a category and returns the new value."""

        async def _inc(tx, cat_id: str):
            query = (
                f"MATCH (c:{self.LABEL_CATEGORY} {{id: $id}}) "
                "SET c.insert_counter = c.insert_counter + 1 "
                "RETURN c.insert_counter as counter"
            )
            result = await tx.run(query, id=cat_id)
            record = await result.single()
            return record["counter"] if record else 0

        async with self.driver.session() as session:
            return await session.execute_write(_inc, category_id)

    async def reset_category_counter(self, category_id: str):
        """Resets the insert_counter for a category."""
        await self.update_node_properties(category_id, self.LABEL_CATEGORY, {"insert_counter": 0})

    async def category_exists(self, category_id: str) -> bool:
        """Checks if a category node exists."""

        async def _check(tx):
            query = f"MATCH (c:{self.LABEL_CATEGORY} {{id: $id}}) RETURN count(c) > 0 as exists"
            result = await tx.run(query, id=category_id)
            record = await result.single()
            return record["exists"] if record else False

        async with self.driver.session() as session:
            return await session.execute_read(_check)

    async def get_dirty_categories(self, threshold: int) -> list[str]:
        """Returns IDs of categories that have exceeded the insert threshold."""

        async def _get(tx):
            query = f"MATCH (c:{self.LABEL_CATEGORY}) WHERE c.insert_counter >= $threshold RETURN c.id as id"
            result = await tx.run(query, threshold=threshold)
            return [record["id"] async for record in result]

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    # ========== Session Operations ==========

    async def ensure_session_node(self, session_id: str):
        """Ensures a Session node exists in the graph."""

        async def _create(tx):
            query = (
                f"MERGE (s:{self.LABEL_SESSION} {{id: $id}}) "
                "ON CREATE SET s.created_at = datetime(), s.updated_at = datetime() "
                "ON MATCH SET s.updated_at = datetime()"
            )
            await tx.run(query, id=session_id)

        async with self.driver.session() as session:
            await session.execute_write(_create)

    async def link_to_session(self, node_id: str, session_id: str):
        """Links a node to a specific Session node."""

        async def _link(tx):
            query = (
                f"MATCH (n {{id: $nid}}) MATCH (s:{self.LABEL_SESSION} {{id: $sid}}) MERGE (n)-[:EXTRACTED_FROM]->(s)"
            )
            await tx.run(query, nid=node_id, sid=session_id)

        async with self.driver.session() as session:
            await session.execute_write(_link)

    # ========== Graph Visualization ==========

    async def get_full_graph(self, active_node_ids: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
        """Retrieves all nodes and relationships for visualization."""
        active_ids = set(active_node_ids or [])

        async def _get(tx):
            # Fetch all nodes with their cat0 ancestor for coloring
            # Include Fact nodes (legacy) - they should be treated as Knowledge nodes
            query = (
                f"MATCH (n) WHERE n:{self.LABEL_KNOWLEDGE} OR n:{self.LABEL_CATEGORY} OR n:Fact "
                f"OPTIONAL MATCH (n)-[:{self.REL_BELONGS_TO}|{self.REL_SUB_CATEGORY_OF}]->(p:{self.LABEL_CATEGORY}) "
                f"OPTIONAL MATCH (n)-[:{self.REL_BELONGS_TO}|{self.REL_SUB_CATEGORY_OF}*0..]->(cat0:{self.LABEL_CATEGORY}) "
                f"WHERE cat0 IS NULL OR (cat0)-[:SUB_CATEGORY_OF]->(:Category {{id: 'cat_root'}}) OR cat0.id = 'cat_root' "
                "RETURN n, labels(n) as labels, p.id as parent_id, collect(DISTINCT cat0.id) as cat0_list"
            )
            res = await tx.run(query)
            nodes = []
            async for record in res:
                node_data = dict(record["n"])
                self._cleanup_node_data(node_data)

                # Determine type from labels
                labels = record["labels"]
                # Treat Fact nodes as knowledge nodes (legacy support)
                node_type = "knowledge" if (self.LABEL_KNOWLEDGE in labels or "Fact" in labels) else "category"

                node_data["type"] = node_type
                node_data["parent_id"] = record["parent_id"]

                # Determine cat0: color group
                cat0_list = record["cat0_list"]
                if cat0_list:
                    l1_cats = [cid for cid in cat0_list if cid != "cat_root"]
                    node_data["cat0"] = l1_cats[0] if l1_cats else "cat_root"
                else:
                    node_data["cat0"] = node_data.get("id") or "unknown"

                node_data["is_hot"] = node_data.get("id") in active_ids
                nodes.append(node_data)

            # Fetch all relationships
            # Include Fact nodes in relationships (legacy support)
            rels_query = (
                f"MATCH (a)-[r]->(b) "
                f"WHERE (a:{self.LABEL_KNOWLEDGE} OR a:{self.LABEL_CATEGORY} OR a:Fact) "
                f"AND (b:{self.LABEL_KNOWLEDGE} OR b:{self.LABEL_CATEGORY} OR b:Fact) "
                "RETURN a.id as source, b.id as target, type(r) as edge_label, r.type as type"
            )
            rels_res = await tx.run(rels_query)
            links = [
                {
                    "source": record["source"],
                    "target": record["target"],
                    "edge_label": record["edge_label"],
                    "type": record["type"],
                }
                async for record in rels_res
            ]

            return {"nodes": nodes, "links": links}

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    # ========== Duplicate Detection ==========

    async def find_duplicate_candidates(
        self, node_ids: list[str], threshold: float = 0.88, limit: int = 5, root_id: str | None = None
    ) -> list[tuple[KnowledgeNode, KnowledgeNode]]:
        """
        Finds candidate Knowledge node pairs for merging based on semantic similarity.
        Uses the vector index for efficiency. Optionally filters by root_id for scoped evolution.
        """
        if not node_ids:
            return []

        candidates = []
        async with self.driver.session() as session:
            for nid in node_ids:
                # Get the embedding for the target node
                res = await session.run(f"MATCH (n:{self.LABEL_KNOWLEDGE} {{id: $id}}) RETURN n.embedding, n", id=nid)
                record = await res.single()
                if not record or not record["n.embedding"]:
                    continue

                target_vector = record["n.embedding"]
                node_a_data = dict(record["n"])
                self._cleanup_node_data(node_a_data)
                node_a = KnowledgeNode(**node_a_data)

                # Search for similar nodes in the index
                search_query = (
                    f"CALL db.index.vector.queryNodes('{self.INDEX_KNOWLEDGE}', $top_k, $vector) "
                    "YIELD node, score "
                    f"WHERE node.id <> $id AND score > $threshold "
                )

                if root_id:
                    search_query += (
                        f"AND EXISTS {{ (node)-[:{self.REL_BELONGS_TO}|{self.REL_SUB_CATEGORY_OF}*0..]->"
                        f"(:{self.LABEL_CATEGORY} {{id: $root_id}}) }} "
                    )

                search_query += "RETURN node, score LIMIT 1"

                search_res = await session.run(
                    search_query, id=nid, vector=target_vector, top_k=limit, threshold=threshold, root_id=root_id
                )
                async for search_record in search_res:
                    node_b_data = dict(search_record["node"])
                    self._cleanup_node_data(node_b_data)
                    node_b = KnowledgeNode(**node_b_data)
                    candidates.append((node_a, node_b))

        return candidates

    async def merge_nodes(self, node_a_id: str, node_b_id: str, merged_node: KnowledgeNode):
        """
        Merges two Knowledge nodes into a single synthesized node and redirects relationships.
        """
        # Ensure the merged node exists
        await self.create_knowledge_node(merged_node)

        async def _merge(tx):
            merged_id = merged_node.id

            # Redirect outgoing relationships (excluding BELONGS_TO)
            for source_id in [node_a_id, node_b_id]:
                query = (
                    f"MATCH (source:{self.LABEL_KNOWLEDGE} {{id: $source_id}})-[r]->(target) "
                    f"WHERE type(r) <> '{self.REL_BELONGS_TO}' "
                    f"WITH source, r, target "
                    f"MATCH (merged:{self.LABEL_KNOWLEDGE} {{id: $merged_id}}) "
                    f"MERGE (merged)-[new_r:{self.REL_RELATED}]->(target) "
                    f"SET new_r = properties(r)"
                )
                await tx.run(query, source_id=source_id, merged_id=merged_id)

            # Redirect incoming relationships
            for target_id in [node_a_id, node_b_id]:
                query = (
                    f"MATCH (source)-[r]->(target:{self.LABEL_KNOWLEDGE} {{id: $target_id}}) "
                    f"WITH source, r, target "
                    f"MATCH (merged:{self.LABEL_KNOWLEDGE} {{id: $merged_id}}) "
                    f"MERGE (source)-[new_r:{self.REL_RELATED}]->(merged) "
                    f"SET new_r = properties(r)"
                )
                await tx.run(query, target_id=target_id, merged_id=merged_id)

            # Inherit BELONGS_TO relationships
            query = (
                f"MATCH (source:{self.LABEL_KNOWLEDGE})-[:{self.REL_BELONGS_TO}]->(cat:{self.LABEL_CATEGORY}) "
                f"WHERE source.id IN $ids "
                f"WITH DISTINCT cat "
                f"MATCH (merged:{self.LABEL_KNOWLEDGE} {{id: $merged_id}}) "
                f"MERGE (merged)-[:{self.REL_BELONGS_TO}]->(cat)"
            )
            await tx.run(query, ids=[node_a_id, node_b_id], merged_id=merged_id)

            # Delete old nodes
            query = f"MATCH (n:{self.LABEL_KNOWLEDGE}) WHERE n.id IN $ids DETACH DELETE n"
            await tx.run(query, ids=[node_a_id, node_b_id])

        async with self.driver.session() as session:
            await session.execute_write(_merge)
            logger.info(f"✅ Merged nodes {node_a_id} and {node_b_id} into {merged_node.id}")

    # ========== Utility Operations ==========

    async def get_existing_tags(self) -> list[str]:
        """Retrieves all unique tags present in the graph."""

        async def _get(tx):
            query = f"MATCH (n:{self.LABEL_KNOWLEDGE}) UNWIND n.tags as tag RETURN DISTINCT tag"
            result = await tx.run(query)
            return [record["tag"] async for record in result if record["tag"]]

        async with self.driver.session() as session:
            return await session.execute_read(_get)

    async def delete_node(self, node_id: str):
        """Safely deletes a node and all its relationships."""

        async def _delete(tx):
            await tx.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)

        async with self.driver.session() as session:
            await session.execute_write(_delete)

    async def get_children_of_category(self, category_id: str) -> list[Category | KnowledgeNode]:
        """Retrieves all direct children (categories and knowledge) of a category."""

        async def _get(tx):
            # Get sub-categories
            cat_query = (
                f"MATCH (c:{self.LABEL_CATEGORY})-[:{self.REL_SUB_CATEGORY_OF}]->"
                f"(:{self.LABEL_CATEGORY} {{id: $id}}) RETURN c"
            )
            cat_result = await tx.run(cat_query, id=category_id)
            categories = []
            async for record in cat_result:
                cat_data = dict(record["c"])
                self._cleanup_node_data(cat_data)
                categories.append(Category(**cat_data))

            # Get knowledge nodes
            know_query = (
                f"MATCH (k:{self.LABEL_KNOWLEDGE})-[:{self.REL_BELONGS_TO}]->"
                f"(:{self.LABEL_CATEGORY} {{id: $id}}) RETURN k"
            )
            know_result = await tx.run(know_query, id=category_id)
            knowledge = []
            async for record in know_result:
                node_data = dict(record["k"])
                self._cleanup_node_data(node_data)
                knowledge.append(KnowledgeNode(**node_data))

            return categories + knowledge

        async with self.driver.session() as session:
            return await session.execute_read(_get)


# Singleton instance
graph_service = GraphService()
