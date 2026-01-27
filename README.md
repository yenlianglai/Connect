# Connect

**Connect** is an intelligent knowledge management system that transforms conversations into a living, evolving knowledge graph. Unlike traditional note-taking apps or simple RAG systems, Connect builds persistent memory that grows smarter over time, connecting ideas and experiences into a structured web of knowledge.

![Connect Interface](static/img.png)

## What is Connect?

> *"Creativity is just connecting things. When you ask creative people how they did something, they feel a little guilty because they didn't really do it, they just saw something. It seemed obvious to them after a while. That's because they were able to connect experiences they've had and synthesize new things."*  
> — Steve Jobs

Connect is named after this philosophy: **learning is not just retrieval—it's pattern recognition**. The system is designed for learners, researchers, and knowledge workers who understand that true understanding comes from seeing connections between ideas, not just storing information.

### The Connect Philosophy

Traditional learning systems treat knowledge as isolated facts to be retrieved. Connect recognizes that **real learning happens when we recognize patterns**—when we see how concepts relate, when we discover unexpected connections, and when we synthesize new insights from existing knowledge.

**Connect helps you:**
- **Recognize patterns**: Automatically discover relationships between concepts, revealing hidden connections
- **Speed up insight**: AI accelerates the pattern recognition process, helping you see connections faster
- **Enlighten understanding**: Surface unexpected relationships and synthesize new knowledge from existing nodes
- **Build on experience**: Connect your experiences and knowledge into a web that grows smarter over time

Think of Connect as your **pattern recognition engine**—an AI-powered system that doesn't just store knowledge, but actively helps you see the connections that lead to deeper understanding and creative insights.

---

## Features

### Intelligent Knowledge Extraction
- **Automatic extraction** of key concepts, facts, and insights from chat conversations
- **Structured knowledge nodes** with rich metadata, tags, and relationships
- **User persona tracking** for personal facts, preferences, and habits
- **Category-based organization** with hierarchical taxonomy

### Pattern Recognition & Connection Discovery
- **Interactive knowledge graph** visualization that reveals hidden patterns
- **Semantic relationships** between concepts (prerequisites, examples, similarities)
- **GraphRAG retrieval** combining vector search with graph traversal for deep pattern matching
- **Automatic relationship discovery** that surfaces unexpected connections between ideas
- **AI-powered synthesis** that helps you see patterns you might have missed

### Intelligent Memory Management
- **Tiered memory architecture**: Hot (Redis), Warm (Neo4j), Cold (MongoDB) for optimal pattern matching
- **Context-aware retrieval** that recognizes patterns across categories or the entire graph
- **Proactive relationship discovery** that anticipates connections you might explore
- **Automatic graph evolution** that merges duplicates and reveals deeper patterns through synthesis

### Modern Interface
- **ChatGPT-style UI** with session management
- **Category-based source selection** for focused knowledge retrieval
- **Real-time graph visualization** with interactive node exploration
- **Rich text editor** for manual knowledge refinement
- **Chat interface** with session history and category-based knowledge source selection
- **Node management** with creation, editing, deletion, and manual relationship creation
- **Category hierarchy navigation** for exploring knowledge structure

---

## Technical Architecture

Connect uses a **three-tier memory architecture** to balance speed, depth, and persistence:

### Hot Memory (Redis)
- **Purpose**: Fast, short-term caching of active knowledge nodes
- **Strategy**: ZSET-based LRU for context window management
- **Use Case**: Immediate access to recently discussed concepts

### Warm Memory (Neo4j)
- **Purpose**: Long-term knowledge graph with relationships and embeddings
- **Strategy**: GraphRAG combining vector search with graph traversal
- **Use Case**: Deep semantic retrieval and relationship discovery

### Cold Memory (MongoDB)
- **Purpose**: Raw session logs and message history
- **Strategy**: Persistent storage for audit and context extraction
- **Use Case**: Historical conversation analysis and knowledge extraction

### Core Components

1. **Context Extractor**: Converts chat history into structured graph nodes and discovers relationships—the foundation of pattern recognition
2. **Memory Retriever**: Hybrid retrieval system that doesn't just fetch facts, but recognizes patterns across cache, vector search, and graph traversal
3. **Memory Refresher**: Proactively discovers related concepts and patterns, anticipating connections you might explore
4. **Memory Evolver**: Automatically merges duplicates and synthesizes knowledge, revealing deeper patterns through AI-powered analysis

---

## Tech Stack

### Backend
- **Framework**: FastAPI (Python)
- **Graph Database**: Neo4j 5.18+ with vector indexes
- **Cache**: Redis 7+ with ZSET-based LRU
- **Document Store**: MongoDB for session logs
- **LLM Integration**: 
  - Google Gemini (Structured Output)
  - OpenAI GPT (configurable)
- **Embeddings**: Gemini Embeddings (768 dimensions)

### Frontend
- **Framework**: React + TypeScript
- **UI Library**: Tailwind CSS
- **Graph Visualization**: react-force-graph-2d
- **Rich Text Editor**: MDXEditor
- **State Management**: TanStack Query
- **Build Tool**: Vite

### Infrastructure
- **Containerization**: Docker Compose
- **Package Management**: uv (Python), npm (Node.js)

## Roadmap

### Planned Features

1. **Enhanced Pattern Recognition**
   - Advanced pattern matching algorithms
   - Multi-hop reasoning for complex relationship discovery
   - Temporal pattern awareness across learning journeys

2. **Multimodal Support**
   - Image extraction and analysis
   - Document parsing (PDF, Markdown)
   - Code snippet understanding

3. **LLM Provider Support**
   - LiteLLM integration for unified API
   - Ollama support for local models
   - Multi-provider fallback strategies

4. **MCP (Model Context Protocol) Support**
   - Standardized context exchange
   - Interoperability with other tools
   - Plugin ecosystem

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (with `uv` package manager)
- Node.js 18+ and npm
- Google API Key (for Gemini) or OpenAI API Key

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Connect
   ```

2. **Start infrastructure**
   ```bash
   docker-compose up -d
   ```
   This starts:
   - MongoDB (port 27017)
   - Neo4j (ports 7474, 7687)
   - Redis (port 6379)
   - Mongo Express (port 8082)

3. **Configure environment**
   Create a `.env` file:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=password
   REDIS_URL=redis://localhost:6379
   MONGODB_URL=mongodb://admin:password@localhost:27017/
   MONGODB_DB_NAME=mnemo
   ```

4. **Start backend**
   ```bash
   uv run uvicorn app.main:app --reload --port 8000
   ```

5. **Start frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

6. **Access the application**
   - Frontend: `http://localhost:5173`
   - Backend API: `http://localhost:8000`
   - Neo4j Browser: `http://localhost:7474`
   - API Docs: `http://localhost:8000/docs`

### First Steps

1. **Start a conversation**: Use the chat interface to begin a conversation
2. **Extract knowledge**: After chatting, trigger extraction to build your graph
3. **Explore the graph**: Switch to Graph view to visualize your knowledge
4. **Create nodes manually**: Use the "Create Node" button to add knowledge directly
5. **Refine relationships**: Edit nodes and create manual links between concepts

---

## Documentation

- **API Documentation**: Available at `/docs` when the backend is running
- **Architecture Details**: See inline code documentation
- **Development Guide**: Check `.cursor/skills/mnemo-coding-standards/SKILL.md` for coding standards

---

## Contributing

Connect follows clean code principles:
- Separation of concerns
- Expressive naming
- Simplicity and generalization
- Comprehensive error handling

See the coding standards in `.cursor/skills/mnemo-coding-standards/SKILL.md` for detailed guidelines.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Connect** - Recognizing patterns, one connection at a time.

*"The goal is not just to retrieve knowledge, but to recognize patterns—and AI helps us speed up this process and enlighten our understanding."*
