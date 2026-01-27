# Mnemo: Persistent, Evolving Context for LLMs

Mnemo is a sophisticated memory-augmented LLM system designed for **persistent, evolving context**. Unlike simple RAG systems, Mnemo treats memory as a dynamic graph that grows and optimizes itself over time. It is specifically tailored to act as an **educational helper assistant**, storing structured knowledge and practical experiences rather than just casual chat logs.

---

## 🧠 Tiered Memory Architecture

Mnemo uses a tiered strategy to balance speed and depth:

1.  **Hot Memory (Redis - Short-term):** Fast, vector-less caching of active knowledge nodes and session context. Uses a **ZSET-based LRU strategy** to keep the context window focused.
2.  **Warm Memory (Neo4j - Long-term):** A high-performance knowledge graph. Relationships (structural) and vector embeddings (semantic) are combined using **GraphRAG** for deep retrieval.
3.  **Cold Memory (MongoDB - Persistence):** Raw session logs and message history used for audit and context extraction.

---

## 🛠 Core Components & Logic

### 1. Context Extractor (The Graph Builder)
Triggered via `POST /extract/{session_id}`, this component converts raw chat history into structured graph memory using a **3-step process**:
*   **Step 1: Node Extraction:** The LLM identifies key learning points (Nodes) from a batch of messages, assigning them a `KnowledgeCategory` and descriptive tags.
*   **Step 2: Structural Retrieval:** The system performs a **GraphRAG search** to find existing nodes in the graph that are semantically or structurally related to the new findings.
*   **Step 3: Relationship Decision:** The LLM evaluates the new nodes against retrieved existing knowledge to decide which relationships (e.g., `PREREQUISITE_FOR`, `EXAMPLE_OF`, `SIMILAR_TO`) to create.

### 2. Memory Retriever (The Context Injector)
Integrated into the `/chat` flow, it follows a **Hybrid Retrieval Logic**:
*   **Cache Check:** First, it pulls "active" nodes from the session's **Redis ZSET**.
*   **Reactive Search:** If the cache is insufficient, it performs a **GraphRAG search** in Neo4j (Vector + Graph Traversal + Tag Matching).
*   **Context Synthesis:** It formats the results into a readable prompt prefix for the LLM, ensuring the assistant "remembers" previous lessons.

### 3. Memory Refresher (The Cache Warmer)
Triggered proactively in the background or via `POST /refresh/{session_id}`:
*   **Graph Traversal:** It looks at the "active" nodes in the current session and fetches their neighbors (N-hops) from Neo4j.
*   **Pre-fetching:** It "warms up" the Redis cache by loading these neighbors, anticipating that the user might follow up on related topics.
*   **LRU Pruning:** It enforces a context size limit in Redis to prevent "memory bloat."

### 4. Memory Evolver (The Graph Optimizer)
Triggered by a **"Dirty Buffer" Event** (when a threshold of new nodes is reached) or via `POST /evolve`:
*   **Entity Resolution:** It uses targeted vector searches to find potential duplicate nodes (e.g., "Python loops" vs "Loops in Python").
*   **Conflict Resolution:** The LLM synthesizes conflicting or overlapping information into a single "Merged Node," preserving chronological awareness and merging descriptions.
*   **Atomic Merging:** It updates the graph in Neo4j, redirecting all existing relationships to the new merged entity.

---

## 🔄 The Memory Lifecycle

| Action | Component | When? | Impact |
| :--- | :--- | :--- | :--- |
| **Retrieval** | `MemoryRetriever` | Every Chat Request | Updates "Active" status (score) in Redis (LRU). |
| **Extraction** | `ContextExtractor` | Manual/Post-session API | Persists new Nodes & Relationships to Neo4j. |
| **Warming** | `MemoryRefresher` | Background (Post-Extraction) | Loads structural neighbors from Neo4j into Redis. |
| **Evolution** | `MemoryEvolver` | Every 5-10 New Nodes | Deduplicates and resolves conflicts in the Graph. |

---

## 📂 Project Structure

*   `app/models/nodes.py`: Defines the **Knowledge Taxonomy** (Categories like Algorithms, System Design, etc.) and Node/Relationship schemas.
*   `app/services/graph/neo4j_service.py`: Core GraphRAG logic using `neo4j-graphrag` with **Gemini Embeddings (768 dim)**.
*   `app/services/memory/redis_service.py`: Tiered caching strategy for sessions and global knowledge.
*   `app/core/llm.py`: Centralized LLM interface supporting **Google Gemini (Structured Output)** and OpenAI.

---

## 🚀 Getting Started

1.  **Infrastructure:**
    ```bash
    docker-compose up -d
    ```
    (Starts MongoDB, Neo4j 5.18.1+, Redis, and Mongo Express)

2.  **Environment:**
    Configure `.env` with `GOOGLE_API_KEY`, `NEO4J_URI`, `REDIS_URL`, etc.

3.  **Run:**
    ```bash
    uv run uvicorn app.main:app --reload
    ```

4.  **Visualize:**
    Access Neo4j Browser at `http://localhost:7474` to see your evolving knowledge graph.
