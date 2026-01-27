import asyncio
from unittest.mock import MagicMock, patch

import pytest
from testcontainers.mongodb import MongoDbContainer
from testcontainers.neo4j import Neo4jContainer

from app.core.session.manager import SessionManager
from app.models.nodes import (
    Category,
    NodePlacement,
    BatchPlacementResult,
    HorizontalRelationshipType,
    KnowledgeNode,
    KnowledgeNodeList,
    Relationship,
    RelationshipList,
    VerticalRelationshipType,
)
from app.services.extractor import ContextExtractor
from app.services.graph.neo4j_service import GraphService


@pytest.fixture(scope="module")
def mongodb_container():
    with MongoDbContainer("mongo:latest") as mongo:
        yield mongo


@pytest.fixture(scope="module")
def neo4j_container():
    # Use a version compatible with neo4j-graphrag (5.18.1+)
    with Neo4jContainer("neo4j:5.18.1") as neo4j:
        yield neo4j


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_extractor_educational_flow(mongodb_container, neo4j_container):
    # 1. Setup Services
    mongo_url = mongodb_container.get_connection_url()
    session_mgr = SessionManager(mongodb_url=mongo_url, db_name="test_db")

    neo4j_url = neo4j_container.get_connection_url()
    graph_svc = GraphService(uri=neo4j_url, user="neo4j", password=neo4j_container.password)
    await graph_svc.ensure_vector_index()

    # We patch the global session_manager and graph_service used inside the extractor
    # AND we mock the embedder to avoid OpenAI API calls
    with (
        patch("app.services.extractor.session_manager", session_mgr),
        patch("app.services.extractor.graph_service", graph_svc),
        patch.object(graph_svc.embedder, "embed_query", return_value=[0.1] * 768),
    ):
        extractor = ContextExtractor(graph_svc=graph_svc)

        # 1.5 Seed Taxonomy Root and cat0
        root = Category(id="cat_root", name="Root", summary="Root", level=0)
        await graph_svc.create_category_node(root)
        cat_infra = Category(id="cat_infra", name="Infrastructure", summary="DevOps and Infrastructure", level=1)
        await graph_svc.create_category_node(cat_infra)
        await graph_svc.create_relationship(Relationship(
            source_id="cat_infra", target_id="cat_root", 
            relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF
        ))

        # 2. Seed Mock Data in Neo4j (Long-term Knowledge)
        k8s_node = KnowledgeNode(
            id="infra-k8s-resources",
            session_id="system-seed",
            tags=["kubernetes", "k8s", "resources"],
            description="Knowledge about Kubernetes resource management.",
            content="Kubernetes allows defining CPU/Memory requests and limits for pods.",
        )
        await graph_svc.create_knowledge_node(k8s_node)
        await graph_svc.create_relationship(Relationship(
            source_id=k8s_node.id, target_id="cat_infra",
            relationship_type=VerticalRelationshipType.BELONGS_TO
        ))

        # 3. Create Session History in MongoDB
        session_id = "incident-report-001"
        conversation = [
            ("user", "Penny: hidol反應PROD variant gateway API 時不時timeout"),
            ("user", "Chiyu: 502 開始頻繁出現. readiness/liveness 頻繁過不了"),
        ]
        for role, text in conversation:
            await session_mgr.add_message(session_id, role, text)
        
        # 4. Run Extractor
        mock_nodes = KnowledgeNodeList(
            nodes=[
                KnowledgeNode(
                    tags=["kubernetes", "cpu"],
                    description="Experience with pod CPU exhaustion.",
                    content="Insufficient CPU requests caused variant-gateway pods to hang.",
                    worth_of_learning=0.9,
                )
            ]
        )

        mock_cat_decision = BatchPlacementResult(
            placements=[
                NodePlacement(
                    node_description="Experience with pod CPU exhaustion.",
                    category_id="cat_infra",
                    reasoning="This is clearly about infrastructure."
                )
            ]
        )

        mock_rels = RelationshipList(
            relationships=[
                Relationship(
                    source_id="AUTO_GENERATED", # Will be patched by extractor
                    target_id="infra-k8s-resources",
                    relationship_type=HorizontalRelationshipType.EXAMPLE_OF,
                    reasoning="Practical example of misconfigured K8s resources.",
                )
            ]
        )

        with patch("app.services.extractor.invoke_llm_structured") as mock_invoke:
            # Step 1: Nodes, Step 2: Navigate (cat_infra), Step 3: Relationships
            mock_invoke.side_effect = [mock_nodes, mock_cat_decision, mock_rels]

            await extractor.extract_and_persist(session_id)

        # Verify new node exists via GraphRAG search
        found_nodes = await graph_svc.graph_rag_search(
            query_text="Insufficient CPU requests caused variant-gateway pods to hang.", 
            category_id="cat_infra"
        )
        print(f"DEBUG: found_nodes IDs: {[n.id for n in found_nodes]}")
        assert len(found_nodes) >= 1

        # We want the ID of the node that WASN'T the seed
        new_node_id = next(n.id for n in found_nodes if n.id != "infra-k8s-resources")

        # Verify relationships
        rels = await graph_svc.get_relationships(new_node_id)
        assert any(r["target_id"] == "infra-k8s-resources" for r in rels)

        print("Extractor test passed!")


@pytest.mark.asyncio
async def test_neo4j_connection(neo4j_container):
    """Simple test to ensure Neo4j container is working."""
    url = neo4j_container.get_connection_url()
    graph_svc = GraphService(uri=url, user="neo4j", password=neo4j_container.password)
    await graph_svc.ensure_vector_index()

    with patch.object(graph_svc.embedder, "embed_query", return_value=[0.1] * 768):
        node = KnowledgeNode(tags=["t1"], description="desc", content="cont")
        node.id = "test-node"
        await graph_svc.create_knowledge_node(node)

        found = await graph_svc.graph_rag_search(query_text="cont")
        # Ensure we found at least the node we just created
        assert any(n.id == "test-node" for n in found)
        await graph_svc.close()
