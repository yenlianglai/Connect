import asyncio
from unittest.mock import patch

import pytest
from testcontainers.neo4j import Neo4jContainer

from app.models.nodes import HorizontalRelationshipType, KnowledgeNode, Relationship
from app.services.graph.neo4j_service import GraphService


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
async def test_graph_rag_traversal(neo4j_container):
    """
    Test that GraphRAG search retrieves both the semantically matched node
    AND its structural neighbors.
    """
    url = neo4j_container.get_connection_url()
    graph_svc = GraphService(uri=url, user="neo4j", password=neo4j_container.password)
    await graph_svc.ensure_vector_index()

    # 1. Setup Mock Graph:
    # Node A: Matches the query semantically
    # Node B: Does NOT match the query, but is RELATED to Node A
    node_a = KnowledgeNode(
        id="node-a",
        tags=["k8s"],
        description="Kubernetes Pods",
        content="Pods are the smallest deployable units of computing in Kubernetes.",
    )

    node_b = KnowledgeNode(
        id="node-b",
        tags=["k8s"],
        description="Kubernetes Nodes",
        content="A node is a worker machine in Kubernetes.",
    )

    rel = Relationship(
        source_id="node-a",
        target_id="node-b",
        relationship_type=HorizontalRelationshipType.PART_OF,
        reasoning="Pods run on Nodes.",
    )

    # We mock the embedder to ensure Node A matches and Node B doesn't
    # Vector search works by similarity, so we give them very different embeddings
    emb_a = [0.9] * 768
    emb_b = [0.1] * 768

    def mock_embed_query(text):
        if "Pods" in text:
            return emb_a
        return emb_b

    with patch.object(graph_svc.embedder, "embed_query", side_effect=mock_embed_query):
        # Insert nodes with their specific embeddings
        await graph_svc.create_knowledge_node(node_a)
        await graph_svc.create_knowledge_node(node_b)
        await graph_svc.create_relationship(rel)

        # 2. Perform GraphRAG Search for "Pods"
        # This should find Node A via vector similarity and Node B via Cypher traversal
        results = await graph_svc.graph_rag_search(query_text="Pods")

        # 3. Assertions
        result_ids = [n.id for n in results]

        # Must find Node A (semantic match)
        assert "node-a" in result_ids

        # Must find Node B (structural neighbor via traversal)
        # This confirms the "OPTIONAL MATCH (node)-[:RELATED]-(neighbor)" logic is working
        assert "node-b" in result_ids

        assert len(results) >= 2

        print(f"GraphRAG Traversal Test Passed! Found: {result_ids}")

    await graph_svc.close()
