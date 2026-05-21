# PRD Agent RAG

AI 驱动的产品需求文档（PRD）自动生成工具。

## 项目定位

本项目旨在**大幅缩短产品需求文档的编写时间**，通过 AI 辅助将产品想法快速转化为结构化的 PRD，减少重复性文档工作。

## 核心能力

- **产品想法 → 结构化 PRD**：输入一句话需求，AI 追问关键问题后生成完整产品需求文档
- **RAG 知识库增强**：内置 PRD 方法论、JTBD 框架、RICE 排序等专业文档，提升输出质量
- **流式输出**：AI 实时生成，逐 token 显示，无需等待
- **游客体验**：无需注册即可试用，降低使用门槛

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 单页应用 + Markdown 渲染 |
| 后端 | FastAPI + PydanticAI + SQLite |
| AI 模型 | DeepSeek Chat（OpenAI 兼容 API） |
| 知识库 | ChromaDB + ONNX 本地嵌入 |
| 部署 | Railway（后端）+ Vercel（前端） |

## 在线体验

无需安装，浏览器打开即用：

https://prd-app.refineyourself.asia

支持游客模式（数据不保存）和注册登录（数据持久化）。

## 部署架构

```
用户 → prd-app.refineyourself.asia（Vercel 前端）
                ↓
        Railway（后端 API）
                ↓
          DeepSeek API（AI 模型）
```

## 主要功能

- AI 对话式 PRD 生成与分析
- 内置知识库搜索增强
- Markdown 格式输出
- 用户认证（邮箱注册/登录 + 游客模式）
- 对话历史管理
- 深色/浅色主题切换
- 响应式布局（桌面 + 移动端）

## API 接口

| 路径 | 说明 |
|---|---|
| `POST /api/v1/auth/register` | 用户注册 |
| `POST /api/v1/auth/login` | 用户登录 |
| `POST /api/v1/auth/guest-login` | 游客登录 |
| `GET /api/v1/conversations` | 对话列表 |
| `POST /api/v1/conversations` | 创建对话 |
| `WS /api/v1/ws/agent` | AI Agent 流式对话 |
