# PRD Agent RAG

> AI 驱动的产品需求文档生成工具——输入一句话产品想法，AI 追问需求细节后生成结构化 PRD。  
> 在线体验：https://prd.ryanflow.cloud（游客模式，无需注册）

---

## 项目价值

产品经理写一份规范的 PRD 通常需要 2-3 天——调研竞品、套模板、反复修改格式。这个项目解决的问题是：**把"写文档"的时间压缩到"想清楚"这件事本身**。

用户输入"我想做一个程序员睡眠追踪 App"，系统不是直接丢出一篇 PRD——而是先通过 RAG 检索知识库中的方法论和模板，再通过三阶段对话（理解需求 → 追问澄清 → 生成文档）输出结构化的产品需求文档。

## 技术亮点

### 1. RAG 工具真正参与对话

LLM 在对话过程中自主决定何时调用 `search_documents` 工具检索知识库，而非仅依赖预检索：

```
用户输入 → PydanticAI agent.iter() → LLM 判断是否需要检索
  → 调用 search_documents → ChromaDB 语义检索
  → 结果注入上下文 → LLM 继续生成回复
```

前端同步展示预检索命中了哪些片段、来源文件名和相似度分数——RAG 不是黑盒。

### 2. 三阶段流程：让用户感知进度

System prompt 定义了三个阶段：理解需求 → 追问澄清（至少 3 个问题）→ 生成 PRD。前端用步骤指示器实时显示当前阶段，用户看到 AI 从"正在搜索知识库"到"追问需求细节"再到"生成 PRD 文档"的完整过程。

### 3. PydanticAI Agent 架构 + 流式输出

使用 PydanticAI 构建 Agent 循环（`agent.iter()`），LLM 可在对话中自主调用工具。保留 fallback 降级机制——Agent 路径失败时自动切换为直调 DeepSeek 模式。流式输出通过 `node.stream()` + `stream_text(delta=True)` 实现，首 token 延迟 < 2 秒。

### 4. 无注册体验

游客模式在服务端生成临时 JWT，不查询数据库、不创建用户记录。Session 数据仅存在于内存中，关闭页面即销毁。

## 架构

```
前端 (Vercel / React SPA) → prd.ryanflow.cloud
        ↕ WebSocket + REST（nginx :8080 代理）
后端 (腾讯云 FastAPI + SQLite) → 106.55.55.54:8002
        ↕ HTTP
ChromaDB（向量知识库）    DeepSeek V4-Flash API（Function Calling）
```

关键决策：使用 SQLite 而非 PostgreSQL 是因为项目数据模型简单（用户、对话、消息），不需要分布式事务。RAG 使用 ChromaDB 的本地 ONNX 嵌入，不需要外部 embedding API。

## 快速启动

```bash
cd backend
uv pip install -e .
uv run uvicorn app.main:app --reload --port 8002
```

环境变量见 `.env.example`，至少需要配置 `DEEPSEEK_API_KEY`。

## 项目结构

```
backend/app/
├── agents/prompts.py        # 三阶段 system prompt 设计
├── services/agent_session.py # 主对话流（RAG + 流式输出）
├── services/rag/             # 知识库检索管线
├── api/routes/v1/            # REST + WebSocket 接口
└── core/config.py            # 配置管理（含生产环境校验取舍）
```

## 截图说明

建议截图 3 张：

1. **首页 + 游客入口**：登录页底部的"游客体验"按钮，展示无门槛体验设计
2. **三阶段指示器 + RAG 来源面板**：对话过程中顶部显示当前阶段，底部展示检索到的知识片段
3. **生成完成的 PRD**：AI 输出的结构化 Markdown，包含 6 个标准章节
