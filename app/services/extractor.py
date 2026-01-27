from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from typing import Dict

from app.core.llm import invoke_llm_structured
from app.core.session.manager import SessionManager, session_manager
from app.models.nodes import (
    BatchPlacementResult,
    Category,
    ExtractionResult,
    FactType,
    HorizontalRelationshipType,
    KnowledgeNode,
    Relationship,
    RelationshipList,
    VerticalRelationshipType,
)
from app.prompts.extractor import (
    CATEGORY_DECISION_SYSTEM_PROMPT,
    CATEGORY_DECISION_USER_TEMPLATE,
    NODE_EXTRACTION_SYSTEM_PROMPT,
    NODE_EXTRACTION_USER_TEMPLATE,
    RELATIONSHIP_DECISION_SYSTEM_TEMPLATE,
    RELATIONSHIP_DECISION_USER_TEMPLATE,
)
from app.services.evolver import MemoryEvolver, memory_evolver
from app.services.graph.neo4j_service import GraphService, graph_service
from app.services.memory.redis_service import RedisService, redis_service
from app.services.memory.refresher import MemoryRefresher, memory_refresher

logger = logging.getLogger(__name__)


class ContextExtractor:
    """
    Service responsible for extracting structured knowledge and personal facts from conversation sessions.
    Uses a recursive 'Taxonomy Navigator' to place knowledge into a deep hierarchical tree.
    """

    def __init__(
        self,
        graph_svc: GraphService | None = None,
        refresher: MemoryRefresher | None = None,
        evolver: MemoryEvolver | None = None,
        session_mgr: SessionManager | None = None,
        redis_svc: RedisService | None = None,
    ):
        self.graph = graph_svc or graph_service
        self.refresher = refresher or memory_refresher
        self.evolver = evolver or memory_evolver
        self.session_mgr = session_mgr or session_manager
        self.redis = redis_svc or redis_service

    async def extract_and_persist(self, session_id: str, batch_size: int = 20):
        """High-level entry point to process new messages in a session and update memory."""
        session = await self.session_mgr.get_session(session_id)
        if not session or not session.messages:
            logger.warning(f"No messages found for session {session_id}. Skipping.")
            return

        # 1. ANCHOR: Ensure the session itself is a Category node in the graph
        # This makes every session a 'Branch' in the knowledge base.
        topic_name = session.metadata.get("topic_name") or session_id
        parent_id = session.metadata.get("parent_category_id") or "cat_root"
        
        # Check if this category anchor already exists
        exists = await self.graph.category_exists(session_id)
        if not exists:
            logger.info(f"⚓ Creating session anchor: {topic_name} under {parent_id}")
            # Get parent level to determine ours
            parent_level = 0
            async with self.graph.driver.session() as s:
                res = await s.run("MATCH (c:Category {id: $id}) RETURN c.level as level", id=parent_id)
                rec = await res.single()
                if rec: parent_level = rec["level"]

            await self.graph.create_category_node(Category(
                id=session_id, 
                name=topic_name, 
                summary=f"Collection of knowledge from session: {topic_name}",
                level=parent_level + 1
            ))
            await self.graph.create_relationship(Relationship(
                source_id=session_id, target_id=parent_id,
                relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
                reasoning="Session-based hierarchical anchor."
            ))

        # 2. CURSOR TRACKING: Find only unprocessed messages
        last_cursor = await self.redis.get_extraction_cursor(session_id)
        unprocessed_messages = [m for m in session.messages if str(m.timestamp) > last_cursor] if last_cursor else session.messages

        if not unprocessed_messages:
            logger.info(f"⏭️ Session {session_id} is already fully processed.")
            return

        # 3. FETCH CONTEXT: Retrieve existing nodes from this session branch
        # We look for nodes belonging to THIS session category
        existing_nodes = await self.graph.get_nodes_by_session(session_id)

        # Process new messages in segments
        for i in range(0, len(unprocessed_messages), batch_size):
            segment = unprocessed_messages[i : i + batch_size]
            
            new_nodes = await self._process_conversation_segment(
                segment=segment, 
                session_id=session_id,
                existing_nodes=existing_nodes,
                entry_point_id="cat_root"  # Start from root to navigate to proper domain categories (cat_software_eng, cat_business, etc.)
            )
            
            if new_nodes: existing_nodes.extend(new_nodes)
            
            new_cursor = str(segment[-1].timestamp)
            await self.redis.set_extraction_cursor(session_id, new_cursor)

        await self.refresher.refresh_hot_memory(session_id)

    async def _process_conversation_segment(
        self, 
        segment: list, 
        session_id: str, 
        existing_nodes: list[KnowledgeNode] = None,
        entry_point_id: str = "cat_root"
    ) -> list[KnowledgeNode]:
        """
        Orchestrates the extraction flow for a single segment of the conversation.
        Steps: Brainstorm -> Initialize -> Separate Facts from Knowledge -> Persist -> Weave Semantic Web.
        """
        history_text = "\n".join([f"{m.role}: {m.content}" for m in segment])

        # 1. BRAINSTORM: LLM extracts new concepts or updates existing ones
        extraction = await self._brainstorm_structured_nodes(
            history_text=history_text,
            existing_nodes=existing_nodes
        )
        if not extraction:
            return []

        # 2. INITIALIZE: Sanitize and validate
        all_nodes = self._initialize_knowledge_nodes(extraction.knowledge_nodes, session_id)

        if not all_nodes:
            return []

        # 3. SEPARATE: Facts (tagged with fact_type) vs Knowledge
        fact_nodes = [n for n in all_nodes if any(tag in [ft.value for ft in FactType] for tag in n.tags)]
        knowledge_nodes = [n for n in all_nodes if n not in fact_nodes]

        logger.info(f"📑 Segment: Extracted {len(knowledge_nodes)} knowledge and {len(fact_nodes)} facts.")

        # 4. PERSIST FACTS: Direct routing to User Profile (cat_user)
        if fact_nodes:
            await self._persist_user_facts(fact_nodes)
        
        # 5. PERSIST KNOWLEDGE: Hierarchical routing
        if knowledge_nodes:
            # Map of node_id -> target_category_id
            placement_map = {}
            
            # Divide into 'Updates' and 'New'
            existing_ids = {n.id for n in (existing_nodes or [])}
            updates = [n for n in knowledge_nodes if n.id in existing_ids]
            inserts = [n for n in knowledge_nodes if n.id not in existing_ids]

            # Process Updates
            for node in updates:
                await self.graph.create_knowledge_node(node)
                current_cat = await self.graph.get_node_category(node.id)
                placement_map[node.id] = current_cat or entry_point_id

            # Process Inserts via Taxonomy Navigator
            if inserts:
                node_id_to_desc = {n.id: n.description for n in inserts}
                new_placements = await self._find_optimal_categories_recursively(
                    entry_point_id=entry_point_id, 
                    nodes_to_place=node_id_to_desc
                )
                placement_map.update(new_placements)
                await self._persist_knowledge_to_taxonomy(inserts, new_placements, session_id)
                
            # 5. WEAVE: Create horizontal semantic links
            await self._weave_semantic_relationships(knowledge_nodes, placement_map)
            
            # Throttling to respect API rate limits
            await asyncio.sleep(1.0)

        return all_nodes

    async def _brainstorm_structured_nodes(
        self, 
        history_text: str, 
        existing_nodes: list[KnowledgeNode] = None
    ) -> ExtractionResult | None:
        """Calls the LLM to extract nodes, providing existing session context for consolidation."""
        try:
            allowed_fact_types = ", ".join([t.value for t in FactType])
            
            # Prepare context strings for the LLM to see what's already in this session
            existing_nodes_json = "None"
            if existing_nodes:
                context_data = []
                for n in existing_nodes:
                    # Check if it's a fact node (has fact_type tag)
                    is_fact = any(tag in [ft.value for ft in FactType] for tag in n.tags)
                    if is_fact:
                        context_data.append({
                            "id": n.id, 
                            "description": n.description, 
                            "content": n.content[:100] + "...",
                            "fact_type": [tag for tag in n.tags if tag in [ft.value for ft in FactType]][0]
                        })
                    else:
                        context_data.append({
                            "id": n.id, 
                            "description": n.description, 
                            "content": n.content[:100] + "..."
                        })
                existing_nodes_json = json.dumps(context_data, ensure_ascii=False, indent=2)

            return await invoke_llm_structured(
                messages=[
                    {"role": "system", "content": NODE_EXTRACTION_SYSTEM_PROMPT.format(allowed_fact_types=allowed_fact_types)},
                    {"role": "user", "content": NODE_EXTRACTION_USER_TEMPLATE.format(
                        history_text=history_text,
                        existing_nodes_json=existing_nodes_json
                    )},
                ],
                response_schema=ExtractionResult,
                max_tokens=3000,
            )
        except Exception as e:
            logger.error(f"Brainstorming step failed: {e}")
            return None

    def _initialize_knowledge_nodes(self, nodes: list[KnowledgeNode], session_id: str) -> list[KnowledgeNode]:
        """Prepares extracted knowledge for the graph system, supporting consolidation."""
        valid = []
        for n in nodes:
            if n.worth_of_learning >= 0.6:
                n.session_id = session_id
                # Only generate a new ID if the LLM didn't reuse an existing one
                if not n.id:
                    n.id = str(uuid.uuid4())
                valid.append(n)
        return valid

    async def _persist_user_facts(self, fact_nodes: list[KnowledgeNode]):
        """Saves personal facts (KnowledgeNodes with fact_type tags) strictly under cat_user."""
        for node in fact_nodes:
            # Ensure facts have worth_of_learning = 1.0 (always worth keeping)
            node.worth_of_learning = 1.0
            # Ensure description is set (use content if not provided)
            if not node.description:
                node.description = node.content
            
            await self.graph.create_knowledge_node(node)
            await self.graph.create_relationship(Relationship(
                source_id=node.id,
                target_id="cat_user",
                relationship_type=VerticalRelationshipType.BELONGS_TO,
                reasoning="Permanent persona fact extracted from dialogue."
            ))
            logger.info(f"📍 Profile Update: {node.content[:50]}...")

    async def _find_optimal_categories_recursively(
        self, 
        entry_point_id: str, 
        nodes_to_place: Dict[str, str], 
        depth: int = 0,
        is_new_branch: bool = False
    ) -> Dict[str, str]:
        """
        The 'Taxonomy Navigator': Recursively walks the category tree to find the 
        most granular home for each piece of knowledge.
        
        Rule: If we just created a new category, we MUST converge in the next step
        to prevent single-child deep chains.
        """
        if not nodes_to_place:
            return {}

        # 1. EXPLORE: Get current category context and its existing branches
        sub_categories = await self.graph.get_sub_categories(entry_point_id)
        
        async with self.graph.driver.session() as session:
            res = await session.run("MATCH (c:Category {id: $id}) RETURN c.name as name, c.summary as summary", id=entry_point_id)
            rec = await res.single()
            p_name, p_sum = (rec["name"], rec["summary"]) if rec else ("Root", "Knowledge base")

        # 2. DECIDE: Ask LLM to partition nodes
        # If is_new_branch is True, we add a strict instruction to converge
        system_prompt = CATEGORY_DECISION_SYSTEM_PROMPT
        if is_new_branch:
            system_prompt += "\n\nCRITICAL: This is a newly created category. You MUST select 'STAY_HERE' or an existing sub-category. DO NOT suggest 'NEW_CATEGORY' again."

        try:
            choice = await invoke_llm_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": CATEGORY_DECISION_USER_TEMPLATE.format(
                        parent_name=p_name, parent_summary=p_sum,
                        sub_categories="\n".join([f"- {c.id}: {c.name} ({c.summary})" for c in sub_categories]) or "None",
                        facts_json="\n".join([f"- ID: {nid} | DESC: {text}" for nid, text in nodes_to_place.items()])
                    )}
                ],
                response_schema=BatchPlacementResult,
                max_tokens=1500
            )
            # Small delay to mitigate rate limits in recursion
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Navigation failed at {entry_point_id}: {e}. Staying at parent.")
            return {nid: entry_point_id for nid in nodes_to_place.keys()}

        # 3. EXECUTE: Sort nodes into the next level of recursion or finalize their placement
        final_assignments = {}
        recursive_batches = {} # Map: target_id -> ({node_id: desc}, is_newly_created)
        created_branches = {}  # Track branches created in this call to prevent duplicates
        
        for decision in choice.placements:
            node_id = decision.node_id
            if node_id not in nodes_to_place:
                logger.warning(f"LLM returned unknown node_id: {node_id}. Skipping.")
                continue
            
            node_desc = nodes_to_place[node_id]

            # Force convergence if we are in a new branch and LLM still tried to create a sub-branch
            if is_new_branch and decision.category_id == "NEW_CATEGORY":
                decision.category_id = "STAY_HERE"

            if decision.category_id == "STAY_HERE":
                final_assignments[node_id] = entry_point_id

            elif decision.category_id == "NEW_CATEGORY" and decision.new_category_name:
                # Reuse a branch if the LLM suggested the same name for multiple nodes in this batch
                target_id = next((cid for cid, name in created_branches.items() if name.lower() == decision.new_category_name.lower()), None)
                
                # Also check existing global categories under this parent
                if not target_id:
                    existing_cat = next((c for c in sub_categories if c.name.lower() == decision.new_category_name.lower()), None)
                    if existing_cat: target_id = existing_cat.id

                is_brand_new = False
                if not target_id:
                    target_id = f"cat_{uuid.uuid4().hex[:8]}"
                    await self.graph.create_category_node(Category(
                        id=target_id, name=decision.new_category_name, 
                        summary=decision.new_category_summary or node_desc, 
                        level=depth + 1
                    ))
                    await self.graph.create_relationship(Relationship(
                        source_id=target_id, target_id=entry_point_id,
                        relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
                        reasoning=f"Hierarchical expansion for: {node_desc}"
                    ))
                    created_branches[target_id] = decision.new_category_name
                    is_brand_new = True

                if target_id not in recursive_batches: recursive_batches[target_id] = ({}, is_brand_new)
                recursive_batches[target_id][0][node_id] = node_desc

            elif any(c.id == decision.category_id for c in sub_categories):
                if decision.category_id not in recursive_batches: recursive_batches[decision.category_id] = ({}, False)
                recursive_batches[decision.category_id][0][node_id] = node_desc
            
            else:
                final_assignments[node_id] = entry_point_id

        # 4. RECURSE: Continue the walk
        for child_id, (batch, branch_was_just_created) in recursive_batches.items():
            recursive_results = await self._find_optimal_categories_recursively(
                child_id, batch, depth + 1, is_new_branch=branch_was_just_created
            )
            final_assignments.update(recursive_results)

        # Safety fallback
        for nid in nodes_to_place.keys():
            if nid not in final_assignments:
                final_assignments[nid] = entry_point_id

        return final_assignments

    async def _persist_knowledge_to_taxonomy(self, nodes: list[KnowledgeNode], taxonomy_map: Dict[str, str], session_id: str):
        """Saves technical nodes and their vertical 'BELONGS_TO' links."""
        for node in nodes:
            target_cat_id = taxonomy_map.get(node.id, "cat_root")
            await self.graph.create_knowledge_node(node)
            await self.graph.increment_category_counter(target_cat_id)
            await self.redis.add_active_node_id(session_id, node.id, score=time.time())

            await self.graph.create_relationship(Relationship(
                source_id=node.id,
                target_id=target_cat_id,
                relationship_type=VerticalRelationshipType.BELONGS_TO,
                reasoning=f"Taxonomy placement from session {session_id}"
            ))

    async def _weave_semantic_relationships(self, nodes: list[KnowledgeNode], taxonomy_map: Dict[str, str]):
        """Discovers and persists horizontal semantic links using GraphRAG."""
        try:
            # 1. FIND CANDIDATES: Use GraphRAG to find conceptually related nodes in relevant branches
            candidate_pool = {}
            for node in nodes:
                target_cat_id = taxonomy_map.get(node.id, "cat_root")
                rag_matches = await self.graph.graph_rag_search(
                    query_text=f"{node.description} {node.content}",
                    category_id=target_cat_id,
                    limit=3
                )
                for match in rag_matches:
                    if match.id not in [n.id for n in nodes]:
                        candidate_pool[match.id] = match

            if not candidate_pool and len(nodes) <= 1:
                return

            # 2. LINK: Ask LLM to weave the semantic web between new and candidate nodes
            logger.info(f"🔗 Weaving semantic web for {len(nodes)} new concepts.")
            allowed_types = ", ".join([t.value for t in HorizontalRelationshipType])
            weaving_result = await invoke_llm_structured(
                messages=[
                    {"role": "system", "content": RELATIONSHIP_DECISION_SYSTEM_TEMPLATE.format(allowed_types=allowed_types)},
                    {"role": "user", "content": RELATIONSHIP_DECISION_USER_TEMPLATE.format(
                        new_nodes_json=[n.model_dump(include={"id", "description", "content"}) for n in nodes],
                        relevant_nodes_json=[n.model_dump(include={"id", "description", "tags"}) for n in candidate_pool.values()]
                    )},
                ],
                response_schema=RelationshipList,
                max_tokens=2000,
            )

            # 3. PERSIST: Save the horizontal links
            valid_ids = {n.id for n in nodes}.union(set(candidate_pool.keys()))
            for rel in weaving_result.relationships:
                # Ensure both source and target exist in our context, and it's not a self-loop
                if rel.source_id in valid_ids and rel.target_id in valid_ids and rel.source_id != rel.target_id:
                    # At least one of the nodes must be a 'new' node from this batch to avoid redundant linking of old nodes
                    if rel.source_id in [n.id for n in nodes] or rel.target_id in [n.id for n in nodes]:
                        await self.graph.create_relationship(rel)

        except Exception as e:
            logger.error(f"Semantic weaving failed: {e}")


context_extractor = ContextExtractor()
