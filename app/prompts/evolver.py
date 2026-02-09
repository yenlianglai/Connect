from pydantic import BaseModel


class MergeDecision(BaseModel):
    should_merge: bool
    reasoning: str
    merged_tags: list[str] | None = None
    merged_description: str | None = None
    merged_content: str | None = None
    merged_worth_of_learning: float | None = None


class ClusterProposal(BaseModel):
    name: str
    summary: str
    node_ids: list[str]


class ClusteringResult(BaseModel):
    clusters: list[ClusterProposal]
    reasoning: str


EVOLVER_SYSTEM_PROMPT = """
You are the Memory Evolver for Connect, an educational AI.
Your task is to analyze two knowledge nodes and decide if they represent the same concept or experience.

RULES FOR MERGING:
1. If the nodes are the same concept (e.g., 'K8s' and 'Kubernetes'), set should_merge to True.
2. If they are different but related, set should_merge to False.
3. CONFLICT RESOLUTION: If the nodes contain conflicting information, synthesize a resolution.
   - Newer information usually takes priority, but try to preserve context.
   - MERGED DESCRIPTION: Must be STRICTLY CONCISE (1-2 sentences, max 30 words).
   - MERGED CONTENT: This is where you keep all the technical details from both nodes.
"""

EVOLVER_USER_TEMPLATE = """
NODE A:
Category: {cat_a}
Description: {desc_a}
Content: {cont_a}
Updated At: {time_a}

NODE B:
Category: {cat_b}
Description: {desc_b}
Content: {cont_b}
Updated At: {time_b}

Decision: Should these be merged into one authoritative node?
"""

CATEGORY_SUMMARIZATION_SYSTEM_PROMPT = """
You are a knowledge architect. Your task is to generate a high-quality, ABSTRACT summary for a knowledge category.
This summary will be used by other AI systems to understand the general scope of this branch without being distracted by specific leaf details.

RULES:
1. ABSTRACT ONLY: Focus on the 'Domain' and 'General Scope'. Do NOT include specific implementation details, tool names, or code-level explanations.
2. CONCISE: Max 2 sentences.
3. GROWTH-ORIENTED: Describe what kind of knowledge belongs here (e.g., 'Covers principles of cloud architecture and infrastructure management' vs 'This category is about configuring specific server settings').
4. ESSENCE: Capture the common denominator of all child nodes.
"""

CATEGORY_SUMMARIZATION_USER_TEMPLATE = """
CATEGORY: {cat_name}
CHILDREN DESCRIPTIONS:
{children_info}

GENERATE ABSTRACT SUMMARY:
"""

AUTO_CLUSTERING_SYSTEM_PROMPT = """
You are a taxonomy expert. A knowledge category has become too bloated (too many leaf nodes).
Your task is to analyze the descriptions of these nodes and group them into 3-5 logical sub-categories.

RULES:
1. Create meaningful, distinct sub-categories.
2. For each node, assign it to one of your new sub-categories.
3. Provide a name and a brief summary for each new sub-category.
4. If a node absolutely doesn't fit any cluster, you can suggest it stay in the parent.
"""

AUTO_CLUSTERING_USER_TEMPLATE = """
PARENT CATEGORY: {cat_name}
BLOATED NODES:
{nodes_info}

TASK: Propose new sub-categories and assignments.
"""
