# CLAUDE.md

## Project Overview

**prd_agent_rag** — AI 驱动的产品需求文档生成工具

**Stack:** FastAPI + Pydantic v2, SQLite, PydanticAI, ChromaDB, DeepSeek V4-Flash, React SPA

## Commands

```bash
# Backend
cd backend
uv pip install -e .
uv run uvicorn app.main:app --reload --port 8002
```

环境变量见 `.env.example`，至少需要 `DEEPSEEK_API_KEY`。

## Project Structure

```
backend/app/
├── agents/               # PydanticAI Agent + tools (search_documents)
├── services/agent_session.py  # 主对话流（WebSocket + RAG + 流式输出）
├── services/usage.py     # Token 用量追踪
├── services/rag/         # ChromaDB 向量检索管线
├── api/routes/v1/        # REST + WebSocket 接口
├── db/models/            # SQLAlchemy 模型
└── core/config.py        # 配置管理
frontend/
├── index.html            # React SPA（单文件）
└── vercel.json           # Vercel 反代配置
```
