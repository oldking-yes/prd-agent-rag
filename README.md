# PRD Agent RAG — Product Requirements Analysis System

> **Transform rough product ideas into structured PRDs with RAG-enhanced AI analysis.**

## What It Does

1. **Upload knowledge** — Upload PRD templates, product methodologies, and competitive analysis documents
2. **Describe your idea** — Type a rough product idea (e.g., "I want to build an AI-powered flashcard app")
3. **Get structured PRD** — The AI agent retrieves relevant knowledge, asks clarifying questions, and generates a complete PRD with:
   - Product Overview & Problem Statement
   - User Stories with prioritization
   - Feature List (P0/P1/P2)
   - Technical Considerations
   - Success Metrics

## Why This Matters

Product managers spend **40% of their time** on documentation. This system:
- Eliminates blank-page syndrome with RAG-retrieved templates
- Ensures completeness with systematic clarification
- Produces consistent, structured output every time

## Architecture

### RAG Pipeline
```
User Upload → Document Parser → Text Chunking → Vector Embedding → ChromaDB
                                                                         ↓
User Query → Vector Search (ChromaDB) → Retrieve Top-K Chunks → LLM → PRD Output
```

### Agent Workflow
```
1. User inputs rough idea
2. Agent searches knowledge base (RAG) for relevant templates/methodologies
3. Agent asks ≥3 clarifying questions (target users, core problem, constraints)
4. After clarification, agent generates structured PRD in Markdown
5. PRD is saved to conversation history for future reference
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15 + React 19 + Tailwind CSS v4 |
| Backend | FastAPI + PydanticAI + SQLite |
| Vector DB | ChromaDB (embedded, no external service) |
| Embeddings | DeepSeek Embedding API |
| LLM | DeepSeek Chat (or any OpenAI-compatible API) |
| Auth | JWT (email/password login) |
| Deploy | Vercel (frontend) + VPS (backend, optional) |

## Getting Started

### Prerequisites
- Python 3.11+, Node.js 18+
- A DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com/))

### 1. Backend
```bash
cd backend
uv sync
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY=sk-your-key

# Create database
uv run python -c "
from app.db.base import Base; from app.db.session import engine
from app.db.models.user import User; from app.db.models.conversation import Conversation, Message, ToolCall
from app.db.models.chat_file import ChatFile; from app.db.models.rag_document import RAGDocument
Base.metadata.create_all(bind=engine); print('DB created!')
"

# Start server
uv run uvicorn app.main:app --reload --port 8001
```

### 2. Seed Knowledge Base
```bash
uv run prd_agent_rag rag-ingest ../seed-docs/ --collection prd_templates
```

### 3. Frontend (optional)
```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/login` | Login, returns JWT |
| `POST /api/v1/auth/register` | Register new user |
| `GET/POST /api/v1/conversations` | List/create conversations |
| `GET /api/v1/rag/collections` | List RAG collections |
| `POST /api/v1/rag/collections/{name}/ingest` | Upload document |
| `POST /api/v1/rag/search` | Search knowledge base |
| `WebSocket /ws/agent` | Streaming PRD analysis |

## Key Design Decisions

- **Why ChromaDB?** Embedded vector store — no external database to manage. Perfect for a portfolio project.
- **Why DeepSeek?** Most cost-effective LLM API at $0.14/M tokens vs OpenAI's $2.50/M (gpt-4o-mini).
- **Why ask questions first?** A PRD without context is useless. The agent's clarification phase ensures the output addresses real needs, not surface-level features.
- **Why SQLite?** Zero infrastructure. Single file database, easy to backup and deploy.

## License

MIT
