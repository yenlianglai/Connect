import asyncio
import logging
from app.services.graph.neo4j_service import graph_service
from app.models.nodes import Category, Relationship, VerticalRelationshipType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def seed_taxonomy():
    """Seeds the initial hierarchical taxonomy root and cat0 categories."""
    logger.info("🌱 Seeding taxonomy root...")

    # 1. Ensure Root
    root = Category(
        id="cat_root",
        name="Knowledge Root",
        summary="The starting point for all knowledge in the Mnemo system.",
        level=0
    )
    await graph_service.create_category_node(root)
    logger.info("✅ Root created.")

    # 2. cat0 Categories
    cat0_categories = [
        ("cat_software_eng", "Software Engineering", "Concepts related to coding, architecture, and systems."),
        ("cat_business", "Business & Economics", "Finance, strategy, marketing, and market dynamics."),
        ("cat_science", "Science & Tech", "General science, physics, biology, and emerging technologies."),
        ("cat_humanities", "Humanities & Arts", "Philosophy, history, psychology, and creative arts."),
        ("cat_lifestyle", "Lifestyle & Growth", "Personal development, health, and hobbies."),
        ("cat_user", "User Profile", "Personal facts, preferences, habits, and goals related to the user.")
    ]

    for cid, name, summary in cat0_categories:
        cat = Category(
            id=cid,
            name=name,
            summary=summary,
            level=1
        )
        await graph_service.create_category_node(cat)
        
        # Link to root
        await graph_service.create_relationship(Relationship(
            source_id=cid,
            target_id="cat_root",
            relationship_type=VerticalRelationshipType.SUB_CATEGORY_OF,
            reasoning="Top-level domain in the knowledge taxonomy."
        ))
        logger.info(f"✅ Seeded Category: {name}")

    # 3. Ensure Vector Indexes
    await graph_service.ensure_vector_index()
    logger.info("🚀 Taxonomy seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_taxonomy())

