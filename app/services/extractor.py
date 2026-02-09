from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

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

    async def extract_and_persist(self, session_id: str, category_hint: str | None = None, batch_size: int = 20):
        """
        High-level entry point to process new messages in a session and update memory.

        Args:
            session_id: The session to extract from
            category_hint: Optional natural language category hint for the LLM (e.g., "Frontend", "Marketing")
            batch_size: Number of messages to process at once
        """
        session = await self.session_mgr.get_session(session_id)
        if not session or not session.messages:
            logger.warning(f"[extract] No messages found for session {session_id}. Skipping.")
            return

        msg_count = len(session.messages)
        logger.info(f"[extract] session_id={session_id} messages={msg_count} category_hint={category_hint!r}")

        # CURSOR TRACKING: Find only unprocessed messages
        last_cursor = await self.redis.get_extraction_cursor(session_id)
        unprocessed_messages = (
            [m for m in session.messages if str(m.timestamp) > last_cursor] if last_cursor else session.messages
        )
        logger.debug(f"[extract] last_cursor={last_cursor!r} unprocessed_count={len(unprocessed_messages)}")

        if not unprocessed_messages:
            logger.info(f"[extract] Session {session_id} already fully processed (cursor at last message).")
            return

        # FETCH CONTEXT: Retrieve existing nodes from this session (for consolidation)
        existing_nodes = await self.graph.get_nodes_by_session(session_id)
        logger.debug(f"[extract] existing_nodes from session: {len(existing_nodes)}")

        total_new = 0
        # Process new messages in segments
        for i in range(0, len(unprocessed_messages), batch_size):
            segment = unprocessed_messages[i : i + batch_size]
            seg_idx = i // batch_size + 1
            seg_total = (len(unprocessed_messages) + batch_size - 1) // batch_size
            logger.info(f"[extract] segment {seg_idx}/{seg_total} messages={len(segment)}")

            new_nodes = await self._process_conversation_segment(
                segment=segment,
                session_id=session_id,
                existing_nodes=existing_nodes,
                entry_point_id="cat_root",  # Always start from root for content-based categorization
                category_hint=category_hint,  # Pass hint to LLM for context
            )

            if new_nodes:
                existing_nodes.extend(new_nodes)
                total_new += len(new_nodes)
                logger.debug(f"[extract] segment {seg_idx} produced {len(new_nodes)} nodes (total so far: {total_new})")

            new_cursor = str(segment[-1].timestamp)
            await self.redis.set_extraction_cursor(session_id, new_cursor)

        logger.info(f"[extract] done session_id={session_id} total_new_nodes={total_new} refreshing_hot_memory=True")
        await self.refresher.refresh_hot_memory(session_id)

    async def _process_conversation_segment(
        self,
        segment: list,
        session_id: str,
        existing_nodes: list[KnowledgeNode] = None,
        entry_point_id: str = "cat_root",
        category_hint: str | None = None,
    ) -> list[KnowledgeNode]:
        """
        Orchestrates the extraction flow for a single segment of the conversation.
        Steps: Stage -> Sanitize -> Route -> Persist -> Link.
        """
        history_text = "\n".join([f"{m.role}: {m.content}" for m in segment])
        logger.debug(f"[segment] messages={len(segment)} history_len={len(history_text)}")

        # 1. STAGE: LLM extracts raw nodes (consolidates with session context)
        extraction = await self._stage_extraction(history_text=history_text, existing_nodes=existing_nodes)
        if not extraction:
            logger.warning("[segment] Stage: no extraction result from LLM (null or empty).")
            return []
        raw_count = len(extraction.knowledge_nodes)
        if raw_count == 0:
            logger.warning(
                "[segment] Stage: LLM returned zero knowledge_nodes. "
                "If using Ollama, try a larger model (e.g. llama3.1, mistral) or ensure the model supports structured JSON output."
            )
            return []
        logger.info(f"[segment] Stage: LLM returned {raw_count} node(s)")
        for idx, n in enumerate(extraction.knowledge_nodes):
            logger.debug(
                f"[segment]   raw[{idx}] id={n.id} desc={(n.description or '')[:60]!r} worth={n.worth_of_learning}"
            )

        # 2. SANITIZE: Validate, normalize tags, and fix descriptions
        all_nodes = self._sanitize_nodes(extraction.knowledge_nodes, session_id)
        if not all_nodes:
            logger.warning(
                "[segment] Sanitize: all %d node(s) filtered out (empty content or invalid).",
                raw_count,
            )
            return []
        if len(all_nodes) < raw_count:
            logger.info(
                f"[segment] Sanitize: kept {len(all_nodes)} of {raw_count} nodes (dropped {raw_count - len(all_nodes)})"
            )
        else:
            logger.debug(f"[segment] Sanitize: kept all {len(all_nodes)} nodes")

        # 3. ROUTE: Separate User Facts from Technical Knowledge
        fact_nodes = [n for n in all_nodes if any(tag in [ft.value for ft in FactType] for tag in n.tags)]
        knowledge_nodes = [n for n in all_nodes if n not in fact_nodes]
        logger.info(
            f"[segment] Route: {len(fact_nodes)} fact(s) -> cat_user, {len(knowledge_nodes)} knowledge -> taxonomy"
        )

        # 4. PERSIST USER FACTS: Direct route to cat_user
        if fact_nodes:
            logger.debug(f"[segment] Persist facts: {len(fact_nodes)} node(s) -> cat_user")
            await self._persist_user_facts(fact_nodes)

        # 5. PERSIST KNOWLEDGE: Hierarchical placement and semantic weaving
        if knowledge_nodes:
            # Map of node_id -> final_category_id
            placement_map = {}

            # Separate into Updates vs Inserts
            existing_ids = {n.id for n in (existing_nodes or [])}
            updates = [n for n in knowledge_nodes if n.id in existing_ids]
            inserts = [n for n in knowledge_nodes if n.id not in existing_ids]
            logger.info(
                f"[segment] Placement: {len(updates)} update(s) (keep category), {len(inserts)} insert(s) (navigate taxonomy)"
            )

            # Process Updates (keep current category)
            for node in updates:
                await self.graph.create_knowledge_node(node)
                current_cat = await self.graph.get_node_category(node.id)
                placement_map[node.id] = current_cat or entry_point_id
                logger.debug(f"[segment]   update node={node.id} -> cat={placement_map[node.id]}")

            # Process Inserts via Taxonomy Navigator
            if inserts:
                # Provide rich context (ID, Desc, Tags, Content Preview) for better categorization
                nodes_to_route = {
                    n.id: {
                        "description": n.description,
                        "tags": n.tags,
                        "content_preview": n.content[:300] + ("..." if len(n.content) > 300 else ""),
                    }
                    for n in inserts
                }
                new_placements = await self._navigate_taxonomy(
                    entry_point_id=entry_point_id,
                    nodes_to_place=nodes_to_route,
                    category_hint=category_hint,
                )
                placement_map.update(new_placements)
                for nid, cid in new_placements.items():
                    logger.debug(f"[segment]   place node={nid} -> cat={cid}")
                await self._persist_knowledge_to_taxonomy(inserts, new_placements, session_id)
                logger.info(f"[segment] Persist: {len(inserts)} node(s) written to Neo4j and Redis hot set")

            # 6. LINK: Weave horizontal semantic web
            await self._link_semantic_nodes(knowledge_nodes, placement_map)

        return all_nodes

    async def _stage_extraction(
        self, history_text: str, existing_nodes: list[KnowledgeNode] = None
    ) -> ExtractionResult | None:
        """Calls the LLM to extract nodes, providing existing session context for consolidation."""
        try:
            existing_count = len(existing_nodes) if existing_nodes else 0
            logger.debug(
                f"[stage] Calling LLM for extraction existing_nodes={existing_count} history_len={len(history_text)}"
            )
            allowed_fact_types = ", ".join([t.value for t in FactType])

            # Prepare context strings for the LLM to see what's already in this session
            existing_nodes_json = "None"
            if existing_nodes:
                context_data = []
                for n in existing_nodes:
                    # Check if it's a fact node
                    is_fact = any(tag in [ft.value for ft in FactType] for tag in n.tags)
                    context_data.append(
                        {
                            "id": n.id,
                            "description": n.description,
                            "content": n.content[:100] + "...",
                            "fact_type": [tag for tag in n.tags if tag in [ft.value for ft in FactType]][0]
                            if is_fact
                            else None,
                        }
                    )
                existing_nodes_json = json.dumps(context_data, ensure_ascii=False, indent=2)

            extraction_result = await invoke_llm_structured(
                messages=[
                    {
                        "role": "system",
                        "content": NODE_EXTRACTION_SYSTEM_PROMPT.format(allowed_fact_types=allowed_fact_types),
                    },
                    {
                        "role": "user",
                        "content": NODE_EXTRACTION_USER_TEMPLATE.format(
                            history_text=history_text, existing_nodes_json=existing_nodes_json
                        ),
                    },
                ],
                response_schema=ExtractionResult,
                max_tokens=6000,
            )
            if extraction_result:
                logger.debug(f"[stage] LLM returned {len(extraction_result.knowledge_nodes)} knowledge_nodes")
            return extraction_result
        except Exception as e:
            logger.error(f"[stage] Staging step failed: {e}", exc_info=True)
            return None

    def _sanitize_nodes(self, nodes: list[KnowledgeNode], session_id: str) -> list[KnowledgeNode]:
        """Validates, normalizes, and prepares extracted nodes for persistence."""
        valid = []
        dropped = 0
        for n in nodes:
            # Require non-empty content
            if not n.content or not n.content.strip():
                dropped += 1
                logger.debug("[sanitize] drop id=%s desc=%s reason=empty_content", n.id, (n.description or "")[:50])
                continue

            # Facts are always kept. For knowledge, require minimum value or boost LLM output that omitted it
            is_fact = any(tag in [ft.value for ft in FactType] for tag in n.tags)
            if not is_fact and n.worth_of_learning < 0.6:
                # LLM often omits or under-sets worth_of_learning; treat extractable content as worth keeping
                prev = n.worth_of_learning
                n.worth_of_learning = 0.8
                logger.debug(
                    "[sanitize] boost worth id=%s desc=%s was=%.2f -> 0.8", n.id, (n.description or "")[:50], prev
                )

            n.session_id = session_id
            if not n.id:
                n.id = str(uuid.uuid4())

            # Clean up description and content
            self._fix_node_metadata(n)
            self._normalize_tags(n)
            self._validate_user_fact_classification(n)

            valid.append(n)
        if dropped:
            logger.debug(f"[sanitize] dropped={dropped} kept={len(valid)} total_input={len(nodes)}")
        return valid

    def _fix_node_metadata(self, node: KnowledgeNode):
        """Fixes description and content issues like length and duplication."""
        # Ensure description exists
        if not node.description or not node.description.strip():
            node.description = node.content[:60].strip() + ("..." if len(node.content) > 60 else "")

        # Relaxed description limits: 15 words for technical context
        desc_words = node.description.split()
        if len(desc_words) > 15:
            node.description = " ".join(desc_words[:12]) + "..."

        # Content-Description duplication check
        desc_lower = node.description.lower().strip()
        content_start = node.content[: len(node.description) + 20].lower().strip()

        if desc_lower == content_start[: len(desc_lower)]:
            # Description is just a slice of content - summarize better
            node.description = " ".join(node.content.split()[:10]) + "..."

    def _normalize_tags(self, node: KnowledgeNode):
        """Standardizes tags: lowercase, underscores, unique."""
        if not node.tags:
            return

        normalized = []
        for tag in node.tags:
            tag_str = str(tag).strip().lower()
            tag_str = tag_str.replace(" ", "_")
            normalized.append(tag_str)

        # Unique tags only
        node.tags = sorted(set(normalized))

    def _validate_user_fact_classification(self, node: KnowledgeNode):
        """Prevents objective technical knowledge from being tagged as a User Fact."""
        fact_tags = [t for t in node.tags if t in [ft.value for ft in FactType]]
        if not fact_tags:
            return

        technical_indicators = [
            "manages",
            "dependencies",
            "framework",
            "api",
            "library",
            "tool",
            "implementation",
            "solution",
        ]
        content_lower = node.content.lower()

        if any(ind in content_lower for ind in technical_indicators):
            logger.warning(f"⚠️ Reclassifying technical node incorrectly tagged as fact: {node.description}")
            node.tags = [t for t in node.tags if t not in [ft.value for ft in FactType]]

    async def _persist_user_facts(self, fact_nodes: list[KnowledgeNode]):
        """Saves personal facts (KnowledgeNodes with fact_type tags) strictly under cat_user."""
        for node in fact_nodes:
            # Ensure facts have worth_of_learning = 1.0 (always worth keeping)
            node.worth_of_learning = 1.0
            # Ensure description is set (use content if not provided)
            if not node.description:
                node.description = node.content

            await self.graph.create_knowledge_node(node)
            await self.graph.create_relationship(
                Relationship(
                    source_id=node.id,
                    target_id="cat_user",
                    relationship_type=VerticalRelationshipType.BELONGS_TO,
                    reasoning="Permanent persona fact extracted from dialogue.",
                )
            )
            logger.info(f"[persist_facts] node={node.id} -> cat_user desc={(node.description or '')[:50]!r}")
        logger.debug(f"[persist_facts] Wrote {len(fact_nodes)} fact(s) to cat_user")

    async def _navigate_taxonomy(
        self,
        entry_point_id: str,
        nodes_to_place: dict[str, dict],
        depth: int = 0,
        is_new_branch: bool = False,
        category_hint: str | None = None,
    ) -> dict[str, str]:
        """
        Recursively finds the optimal category for each node.
        Rich Context: Passes {id: {desc, tags}} to LLM for better mapping.
        """
        if not nodes_to_place:
            return {}

        logger.debug(
            f"[taxonomy] entry={entry_point_id} depth={depth} nodes={len(nodes_to_place)} is_new_branch={is_new_branch}"
        )

        # 1. FETCH: Current parent context and existing children
        sub_categories = await self.graph.get_sub_categories(entry_point_id)
        async with self.graph.driver.session() as session:
            res = await session.run(
                "MATCH (c:Category {id: $id}) RETURN c.name as name, c.summary as summary", id=entry_point_id
            )
            rec = await res.single()
            p_name, p_sum = (rec["name"], rec["summary"]) if rec else ("Root", "Knowledge base")

        # 2. DECIDE: LLM partitions nodes into sub-categories or NEW ones
        system_prompt = CATEGORY_DECISION_SYSTEM_PROMPT
        if category_hint and depth == 0:
            system_prompt += f"\n\nUSER HINT: Content relates to '{category_hint}'."
        if is_new_branch:
            system_prompt += "\n\nCRITICAL: Already in new branch. DO NOT create more new categories here."

        try:
            choice = await invoke_llm_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": CATEGORY_DECISION_USER_TEMPLATE.format(
                            parent_name=p_name,
                            parent_summary=p_sum,
                            sub_categories="\n".join([f"- {c.id}: {c.name} ({c.summary})" for c in sub_categories])
                            or "None",
                            items_json=json.dumps(nodes_to_place, indent=2),
                        ),
                    },
                ],
                response_schema=BatchPlacementResult,
                max_tokens=3000,
            )
            await asyncio.sleep(0.5)
            for p in choice.placements:
                logger.debug(
                    f"[taxonomy] decision node_id={p.node_id} category_id={p.category_id!r} new_name={getattr(p, 'new_category_name', None)!r}"
                )
        except Exception as e:
            logger.warning(f"[taxonomy] Navigation failed at {entry_point_id}: {e}")
            # When at root, put technical content under Software Engineering instead of root
            fallback_cat = "cat_software_eng" if entry_point_id == "cat_root" else entry_point_id
            return dict.fromkeys(nodes_to_place.keys(), fallback_cat)

        # 3. PROCESS DECISIONS
        final_placements = {}
        recursive_batches = {}  # target_id -> ({node_id: context}, is_new)
        created_branches = {}

        for decision in choice.placements:
            node_id = decision.node_id
            if node_id not in nodes_to_place:
                continue

            cat_id = decision.category_id

            # Validation & Fallbacks
            if cat_id == "NEW_CATEGORY" and decision.new_category_name:
                # Reuse if same name suggested in batch
                target_id = next(
                    (
                        cid
                        for cid, name in created_branches.items()
                        if name.lower() == decision.new_category_name.lower()
                    ),
                    None,
                )
                if not target_id:
                    target_id = f"cat_{uuid.uuid4().hex[:8]}"
                    await self.graph.create_category_node(
                        Category(
                            id=target_id,
                            name=decision.new_category_name,
                            summary=decision.new_category_summary or nodes_to_place[node_id]["desc"],
                            level=depth + 1,
                        )
                    )
                    await self.graph.create_relationship(
                        Relationship(
                            source_id=target_id,
                            target_id=entry_point_id,
                            relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
                        )
                    )
                    created_branches[target_id] = decision.new_category_name

                if target_id not in recursive_batches:
                    recursive_batches[target_id] = ({}, True)
                recursive_batches[target_id][0][node_id] = nodes_to_place[node_id]

            elif any(c.id == cat_id for c in sub_categories) or cat_id.startswith("cat_"):
                if cat_id not in recursive_batches:
                    recursive_batches[cat_id] = ({}, False)
                recursive_batches[cat_id][0][node_id] = nodes_to_place[node_id]
            else:
                final_placements[node_id] = entry_point_id

        # 4. RECURSE
        for child_id, (batch, is_new) in recursive_batches.items():
            recursive_results = await self._navigate_taxonomy(child_id, batch, depth + 1, is_new_branch=is_new)
            final_placements.update(recursive_results)

        # Final safety
        for nid in nodes_to_place:
            if nid not in final_placements:
                final_placements[nid] = entry_point_id
                logger.debug(f"[taxonomy] fallback node={nid} -> {entry_point_id}")

        logger.debug(f"[taxonomy] final_placements={list(final_placements.items())}")
        return final_placements

    async def _persist_knowledge_to_taxonomy(
        self, nodes: list[KnowledgeNode], taxonomy_map: dict[str, str], session_id: str
    ):
        """Saves technical nodes and their vertical 'BELONGS_TO' links."""
        logger.debug(f"[persist] Writing {len(nodes)} node(s) to Neo4j and Redis")
        for node in nodes:
            target_cat_id = taxonomy_map.get(node.id, "cat_root")
            await self.graph.create_knowledge_node(node)
            await self.graph.increment_category_counter(target_cat_id)
            await self.redis.add_active_node_id(session_id, node.id, score=time.time())

            await self.graph.create_relationship(
                Relationship(
                    source_id=node.id,
                    target_id=target_cat_id,
                    relationship_type=VerticalRelationshipType.BELONGS_TO,
                    reasoning=f"Taxonomy placement from session {session_id}",
                )
            )
            logger.debug(f"[persist] node={node.id} -> cat={target_cat_id} desc={(node.description or '')[:40]!r}")

    async def _link_semantic_nodes(self, nodes: list[KnowledgeNode], placement_map: dict[str, str]):
        """Discovers and persists horizontal semantic links using GraphRAG."""
        try:
            # 1. FIND CANDIDATES via GraphRAG
            candidate_pool = {}
            for node in nodes:
                rag_matches = await self.graph.graph_rag_search(
                    query_text=f"{node.description} {node.content}",
                    category_id=placement_map.get(node.id, "cat_root"),
                    limit=3,
                )
                for match in rag_matches:
                    if match.id not in [n.id for n in nodes]:
                        candidate_pool[match.id] = match

            logger.debug(f"[link] new_nodes={len(nodes)} candidate_pool={len(candidate_pool)}")

            if not candidate_pool and len(nodes) <= 1:
                logger.debug("[link] Skip: no candidates or single node")
                return

            # 2. LINK via LLM
            logger.info(
                f"[link] Weaving semantic web for {len(nodes)} new concept(s), {len(candidate_pool)} candidate(s)."
            )
            allowed_types = ", ".join([t.value for t in HorizontalRelationshipType])
            weaving_result = await invoke_llm_structured(
                messages=[
                    {
                        "role": "system",
                        "content": RELATIONSHIP_DECISION_SYSTEM_TEMPLATE.format(allowed_types=allowed_types),
                    },
                    {
                        "role": "user",
                        "content": RELATIONSHIP_DECISION_USER_TEMPLATE.format(
                            new_nodes_json=[n.model_dump(include={"id", "description", "content"}) for n in nodes],
                            relevant_nodes_json=[
                                n.model_dump(include={"id", "description", "tags"}) for n in candidate_pool.values()
                            ],
                        ),
                    },
                ],
                response_schema=RelationshipList,
                max_tokens=2000,
            )

            # 3. PERSIST: Save horizontal links
            valid_ids = {n.id for n in nodes}.union(set(candidate_pool.keys()))
            created = 0
            for rel in weaving_result.relationships:
                if rel.source_id in valid_ids and rel.target_id in valid_ids and rel.source_id != rel.target_id:
                    # At least one must be a 'new' node
                    if rel.source_id in [n.id for n in nodes] or rel.target_id in [n.id for n in nodes]:
                        await self.graph.create_relationship(rel)
                        created += 1
                        logger.debug(f"[link] rel {rel.source_id} --{rel.relationship_type}-> {rel.target_id}")
            logger.info(
                f"[link] Created {created} horizontal relationship(s) (LLM suggested {len(weaving_result.relationships)})"
            )

        except Exception as e:
            logger.error(f"[link] Semantic linking failed: {e}", exc_info=True)


context_extractor = ContextExtractor()
