# PRD Agent RAG

> AI 驱动的产品需求文档生成工具——输入一句话产品想法，AI 追问需求细节后生成结构化 PRD。  
> 在线体验：https://prd-app.refineyourself.asia（游客模式，无需注册）

---

## 项目价值

产品经理写一份规范的 PRD 通常需要 2-3 天——调研竞品、套模板、反复修改格式。这个项目解决的问题是：**把"写文档"的时间压缩到"想清楚"这件事本身**。

用户输入"我想做一个程序员睡眠追踪 App"，系统不是直接丢出一篇 PRD——而是先通过 RAG 检索知识库中的方法论和模板，再通过三阶段对话（理解需求 → 追问澄清 → 生成文档）输出结构化的产品需求文档。

## 技术亮点

### 1. RAG 管线：检索不是黑盒

每次用户输入，系统先在 ChromaDB 中检索相关知识片段（相似度排序），将结果注入 system prompt，再调用 LLM 生成。

```
用户输入 → 语义检索(ChromaDB + ONNX) → 命中片段注入 prompt → DeepSeek 流式生成
```

前端同步展示命中了哪些片段、来源文件名和相似度分数——RAG 不是黑盒。

**取舍**：选择了预检索（pre-retrieval）而非 Agent 工具调用的方式。原因有二：DeepSeek Chat API 不支持 tool calling；PRD 生成需要模板前置参考，不适合生成过程中动态检索。

### 2. 三阶段流程：让用户感知进度

System prompt 定义了三个阶段：理解需求 → 追问澄清（至少 3 个问题）→ 生成 PRD。前端用步骤指示器实时显示当前阶段，用户看到 AI 从"正在搜索知识库"到"追问需求细节"再到"生成 PRD 文档"的完整过程。

### 3. 单条主路径 + 流式输出

只保留一条主路径（httpx 直接调用 DeepSeek stream API），没有 Agent fallback，没有工具调用循环。每条文本 chunk 到达即推送到前端，用户从输入到看到第一个 token 不超过 2 秒。

### 4. 无注册体验

游客模式在服务端生成临时 JWT，不查询数据库、不创建用户记录。Session 数据仅存在于内存中，关闭页面即销毁。

## 架构

```
前端 (Vercel / React SPA)
        ↕ WebSocket + REST
后端 (Railway / FastAPI + SQLite)
        ↕ HTTP
ChromaDB(知识库)    DeepSeek API(AI模型)
```

关键决策：使用 SQLite 而非 PostgreSQL 是因为项目数据模型简单（用户、对话、消息），不需要分布式事务。RAG 使用 ChromaDB 的本地 ONNX 嵌入，不需要外部 embedding API。

## 快速启动

```bash
cd backend
pip install -e .
uvicorn app.main:app --reload --port 8001
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
