# PRD Agent RAG 🚀

AI 驱动的产品需求文档（PRD）自动生成工具。输入产品想法，AI 帮你生成结构化产品需求文档。

## 技术栈

- **后端**: FastAPI + PydanticAI + SQLite
- **AI 模型**: DeepSeek Chat (OpenAI 兼容 API)
- **RAG**: ChromaDB + 本地 ONNX 嵌入模型
- **前端**: 单页 HTML (React 18 + Marked)
- **部署**: Zeabur (后端) + Vercel (前端)

## 部署架构

```
用户 → prd-app.refineyourself.asia (Vercel/前端)
                ↓
        prd-api.refineyourself.asia (Zeabur/后端 API)
                ↓
            DeepSeek API (AI 模型)
```

## 快速开始

### 本地开发

```bash
# 后端
cd backend
uv run uvicorn app.main:app --reload --port 8001

# 前端（直接浏览器打开）
# 访问 http://localhost:8001
```

### 环境变量

创建 `backend/.env`：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
AI_MODEL=deepseek-chat
ENVIRONMENT=development
FRONTEND_URL=http://localhost:5173
```

## 功能

- 💬 **AI 对话式 PRD 生成** — 输入产品想法，AI 追问关键问题后生成完整 PRD
- 📚 **RAG 知识库** — 内置 PRD 方法论、JTBD 框架、RICE 排序等文档，提升生成质量
- ⚡ **流式输出** — AI 回复实时逐 token 显示
- 🔐 **用户认证** — 邮箱注册/登录，JWT 鉴权
- 📝 **Markdown 输出** — PRD 以 Markdown 格式呈现
- 🌐 **中英文界面** — 自动适配

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/routes/v1/       # API 路由
│   ├── agents/              # AI Agent 定义
│   ├── services/            # 业务逻辑 (RAG, Agent Session)
│   ├── core/config.py       # 配置管理
│   └── db/                  # 数据库模型
├── Dockerfile               # 容器化部署
└── .env.example             # 环境变量模板

frontend/
└── index.html               # 单页前端 (React + CDN)
```

## API 接口

| 路径 | 说明 |
|------|------|
| `POST /api/v1/auth/register` | 用户注册 |
| `POST /api/v1/auth/login` | 用户登录 |
| `GET /api/v1/conversations` | 对话列表 |
| `POST /api/v1/conversations` | 创建对话 |
| `WS /api/v1/ws/agent` | AI Agent WebSocket 流式对话 |

完整 API 文档见 `/docs`（开发环境）。

## 部署

### 后端 (Zeabur)

1. Fork 仓库并在 Zeabur 导入
2. 设置环境变量：
   - `DEEPSEEK_API_KEY`
   - `FRONTEND_URL`
   - `ENVIRONMENT` = `production`
   - `SECRET_KEY` = 随机 64 位 hex 字符串
3. 配置自定义域名

### 前端 (Vercel)

1. 连接 GitHub 仓库
2. 设置 `public` 目录
3. 配置自定义域名

## License

MIT
