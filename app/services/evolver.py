import logging
import uuid
from datetime import UTC, datetime

from app.core.llm import invoke_llm, invoke_llm_structured
from app.models.nodes import Category, KnowledgeNode, Relationship, VerticalRelationshipType
from app.prompts.evolver import (
    AUTO_CLUSTERING_SYSTEM_PROMPT,
    AUTO_CLUSTERING_USER_TEMPLATE,
    CATEGORY_SUMMARIZATION_SYSTEM_PROMPT,
    CATEGORY_SUMMARIZATION_USER_TEMPLATE,
    EVOLVER_SYSTEM_PROMPT,
    EVOLVER_USER_TEMPLATE,
    ClusteringResult,
    MergeDecision,
)
from app.services.graph.neo4j_service import GraphService, graph_service
from app.services.memory.redis_service import RedisService, redis_service

logger = logging.getLogger(__name__)


class MemoryEvolver:
    """
    Service responsible for evolving the knowledge graph by merging duplicate
    or highly similar nodes and resolving conflicts within specific subtrees.
    """

    def __init__(
        self, threshold: int = 5, graph_svc: GraphService | None = None, redis_svc: RedisService | None = None
    ):
        self.threshold = threshold
        self.is_running = False
        self.graph = graph_svc or graph_service
        self.redis = redis_svc or redis_service

    async def evolve(self):
        """
        Global evolution trigger: Scans for branches that have exceeded the growth threshold.
        """
        if self.is_running:
            return

        self.is_running = True
        logger.info(f"🚀 Scanning for dirty branches (threshold={self.threshold})...")

        try:
            # 1. Identify categories that have grown too fast
            dirty_category_ids = await self.graph.get_dirty_categories(threshold=self.threshold)

            if not dirty_category_ids:
                logger.info("✨ No dirty branches found.")
                return

            for cat_id in dirty_category_ids:
                await self.evolve_subtree(cat_id)

        except Exception as e:
            logger.error(f"Error during evolution: {e}")
        finally:
            self.is_running = False
            logger.info("✅ Evolution scan finished.")

    async def evolve_subtree(self, root_id: str, BLOAT_THRESHOLD: int = 20):
        """
        Localized evolution logic: Deduplicates, Checks for Bloat, and Re-summarizes.
        """
        logger.info(f"🔄 Evolving subtree: {root_id}")

        # 1. Fetch all nodes in this category
        nodes = await self.graph.get_category_nodes(root_id)
        if not nodes:
            await self.graph.reset_category_counter(root_id)
            return

        # 2. Localized Deduplication (O(N) similarity search via Neo4j Vector Index)
        node_ids = [n.id for n in nodes]
        candidates = await self.graph.find_duplicate_candidates(node_ids, threshold=0.88, root_id=root_id)

        client = await self.redis.get_client()
        for node_a, node_b in candidates:
            # Conflict Resolution via LLM
            decision = await invoke_llm_structured(
                messages=[
                    {"role": "system", "content": EVOLVER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": EVOLVER_USER_TEMPLATE.format(
                            cat_a=root_id,
                            desc_a=node_a.description,
                            cont_a=node_a.content,
                            time_a=node_a.updated_at,
                            cat_b=root_id,
                            desc_b=node_b.description,
                            cont_b=node_b.content,
                            time_b=node_b.updated_at,
                        ),
                    },
                ],
                response_schema=MergeDecision,
            )

            if decision.should_merge:
                logger.info(f"Merging: {node_a.id} + {node_b.id}")
                merged_node = KnowledgeNode(
                    id=node_a.id,
                    tags=decision.merged_tags or list(set(node_a.tags + node_b.tags)),
                    description=decision.merged_description or node_a.description,
                    content=decision.merged_content or node_a.content,
                    worth_of_learning=decision.merged_worth_of_learning
                    or max(node_a.worth_of_learning, node_b.worth_of_learning),
                    session_id=node_a.session_id,
                    updated_at=datetime.now(UTC),
                )
                await self.graph.merge_nodes(node_a.id, node_b.id, merged_node)
                await client.delete(f"knowledge:{node_a.id}")
                await client.delete(f"knowledge:{node_b.id}")

        # 3. Check for Bloat (Auto-Splitting)
        if len(nodes) > BLOAT_THRESHOLD:
            await self.split_bloated_subtree(root_id, nodes)

        # 4. Update Category Summary (The RAPTOR Effect)
        await self.re_summarize_subtree(root_id)

        # 5. Clear the dirty counter
        await self.graph.reset_category_counter(root_id)
        logger.info(f"✅ Subtree {root_id} evolution complete.")

    async def split_bloated_subtree(self, root_id: str, nodes: list[KnowledgeNode]):
        """
        Splits a bloated subtree into multiple logical branches using LLM clustering.
        """
        logger.info(f"📂 Branch {root_id} is bloated ({len(nodes)} nodes). Splitting...")

        # 1. Fetch Root Details
        async with self.graph.driver.session() as session:
            res = await session.run("MATCH (c:Category {id: $id}) RETURN c.name as name, c.level as level", id=root_id)
            record = await res.single()
            if not record:
                return
            cat_name, cat_level = record["name"], record["level"]

        # 2. Ask LLM to Cluster
        nodes_info = "\n".join([f"- [{n.id}]: {n.description}" for n in nodes])
        try:
            clustering = await invoke_llm_structured(
                messages=[
                    {"role": "system", "content": AUTO_CLUSTERING_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": AUTO_CLUSTERING_USER_TEMPLATE.format(cat_name=cat_name, nodes_info=nodes_info),
                    },
                ],
                response_schema=ClusteringResult,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error(f"Auto-clustering failed: {e}")
            return

        # 3. Create New Branches and Re-route
        for cluster in clustering.clusters:
            new_cat_id = f"cat_{uuid.uuid4().hex[:8]}"
            await self.graph.create_category_node(
                Category(id=new_cat_id, name=cluster.name, summary=cluster.summary, level=cat_level + 1)
            )

            await self.graph.create_relationship(
                Relationship(
                    source_id=new_cat_id,
                    target_id=root_id,
                    relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
                    reasoning=f"Auto-split from '{cat_name}'",
                )
            )

            for nid in cluster.node_ids:
                # Remove old link and add new one
                async with self.graph.driver.session() as session:
                    await session.run(
                        "MATCH (n:Knowledge {id: $nid})-[r:BELONGS_TO]->(:Category {id: $cid}) DELETE r",
                        nid=nid,
                        cid=root_id,
                    )

                await self.graph.create_relationship(
                    Relationship(
                        source_id=nid,
                        target_id=new_cat_id,
                        relationship_type=VerticalRelationshipType.BELONGS_TO,
                        reasoning="Re-assigned during branch split.",
                    )
                )

        logger.info(f"✅ Splitted {root_id} into {len(clustering.clusters)} sub-branches.")

    async def re_summarize_subtree(self, root_id: str):
        """
        Generates a new summary for a subtree root based on its descendants and propagates upward.
        """
        if root_id == "cat_root":
            return

        # 1. Fetch Root Details
        async with self.graph.driver.session() as session:
            res = await session.run("MATCH (c:Category {id: $id}) RETURN c", id=root_id)
            record = await res.single()
            if not record:
                return
            cat_data = dict(record["c"])

        # 2. Fetch Direct Descendants Info
        async with self.graph.driver.session() as session:
            query = (
                "MATCH (child)-[:BELONGS_TO|SUB_CATEGORY_OF]->(:Category {id: $id}) "
                "RETURN child.description as desc, child.summary as summary, child.name as name"
            )
            result = await session.run(query, id=root_id)
            children_info = []
            async for record in result:
                if record.get("desc"):  # Knowledge
                    children_info.append(f"- {record['desc']}")
                elif record.get("name"):  # Sub-category
                    children_info.append(f"- Branch [{record['name']}]: {record['summary']}")

        if not children_info:
            return

        # 3. Ask LLM to Re-Summarize
        new_summary = await invoke_llm(
            messages=[
                {"role": "system", "content": CATEGORY_SUMMARIZATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": CATEGORY_SUMMARIZATION_USER_TEMPLATE.format(
                        cat_name=cat_data["name"], children_info="\n".join(children_info)
                    ),
                },
            ],
            max_tokens=300,
        )

        # 4. Update Root in Neo4j
        updated_cat = Category(
            id=root_id,
            name=cat_data["name"],
            summary=new_summary,
            level=cat_data["level"],
            updated_at=datetime.now(UTC),
        )
        await self.graph.create_category_node(updated_cat)
        logger.info(f"Updated summary for {root_id}: {new_summary[:50]}...")

        # 5. Propagate Upward
        async with self.graph.driver.session() as session:
            parent_res = await session.run(
                "MATCH (c:Category {id: $id})-[:SUB_CATEGORY_OF]->(p:Category) RETURN p.id as id", id=root_id
            )
            parent_record = await parent_res.single()
            if parent_record:
                await self.re_summarize_subtree(parent_record["id"])


# Singleton instance
memory_evolver = MemoryEvolver(threshold=10)
