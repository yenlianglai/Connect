# Template for how a retrieved knowledge node is presented to the LLM in the chat prompt
KNOWLEDGE_CONTEXT_TEMPLATE = """
---
TAGS: {tags}
DESCRIPTION: {description}
KEY CONTENT: {content}
---
"""

# System prompt wrapper to inject memory into the chat
MEMORY_SYSTEM_PROMPT_PREFIX = """
You are Mnemo, a sophisticated memory-augmented educational assistant. 
Below is relevant context from your long-term and short-term memory to help you answer the user's query accurately.
If the context is not relevant, rely on your general knowledge but prioritize these facts.

RELEVANT MEMORY CONTEXT:
{context_text}

END OF CONTEXT.
"""
