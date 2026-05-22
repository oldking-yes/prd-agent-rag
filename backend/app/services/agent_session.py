
"""Agent session management for WebSocket-based PRD analysis.

Handles the lifecycle of a single agent conversation session:
- Message processing and streaming
- Conversation persistence
- RAG-enhanced PRD generation
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import WebSocket

from app.agents.assistant import PRDAgent
from app.core.config import settings
from app.db.models.user import User
from app.services.agent import send_event
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
)

logger = logging.getLogger(__name__)

# Shared httpx client with connection pooling for DeepSeek API calls
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client with connection pooling."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=120.0, pool=30.0),
            limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=60),
        )
    return _http_client


class AgentSession:
    """Manages a single PRD analysis conversation session."""

    def __init__(
        self,
        websocket: WebSocket,
        user: User,
    ):
        self.websocket = websocket
        self.user = user
        self.conversation_id: str | None = None
        self.db = None
        self.message_history: list[dict[str, str]] = []
        self.phase: str = "understand"
        self._prd_forced: bool = False

    @staticmethod
    def _detect_phase(text: str, message_count: int) -> str:
        """Detect the current PRD generation phase from the response text.

        Returns one of: "understand", "clarify", "generate".
        """
        # First turn → clarify (understand is too brief to track separately)
        if message_count <= 1:
            return "clarify"

        # PRD section headers indicate the generate phase
        prd_patterns = [
            "## 1. Product Overview",
            "## Product Overview",
            "## 1. 产品概述",
            "# PRD Template",
            "### P0 — Must Have",
            "### P0 — 必备",
            "## 4. Technical Considerations",
            "## Success Metrics",
            "## 6. Open Questions",
        ]
        if any(p in text for p in prd_patterns):
            return "generate"

        return "clarify"

    async def process_message(self, data: dict[str, Any]) -> None:
        """Process an incoming message from the WebSocket."""
        user_message = data.get("message", "")
        self.conversation_id = data.get("conversation_id")
        file_ids = data.get("file_ids", [])

        if not user_message.strip():
            return

        # Set up DB session for persistence
        from app.db.session import SessionLocal
        self.db = SessionLocal()

        try:
            # Send status immediately so user sees something
            await send_event(self.websocket, "status", {"status": "thinking"})

            await self._persist_user_message(user_message, file_ids)

            # Pre-retrieve RAG knowledge and inject into system prompt
            agent = PRDAgent()
            base_prompt = agent.system_prompt or "你是一位产品经理，帮助用户分析产品需求并生成 PRD。"

            await send_event(self.websocket, "status", {"status": "generating"})

            rag_context, rag_sources = await self._retrieve_knowledge(user_message)

            if rag_context:
                enhanced_prompt = base_prompt + "\n\n---\n" + rag_context
                await send_event(self.websocket, "rag_context", {"sources": rag_sources})
                await send_event(self.websocket, "phase", {"phase": "understand", "label": "理解需求", "done": False})
            else:
                enhanced_prompt = base_prompt

            messages: list[dict[str, str]] = [{"role": "system", "content": enhanced_prompt}]
            for msg in self.message_history:
                messages.append({"role": msg["role"], "content": msg["content"]})

            # Force PRD generation after 3 user answers.
            if self.conversation_id and self.db:
                from app.repositories import conversation_repo
                total_user_msgs = conversation_repo.count_user_messages(self.db, self.conversation_id)
            else:
                total_user_msgs = sum(1 for m in self.message_history if m["role"] == "user")
            if total_user_msgs >= 3 and not self._prd_forced:
                self._prd_forced = True
                logger.info("PRD_FORCE fired at count=%d", total_user_msgs)
                user_message = user_message + "\n\n[IMPORTANT: You have already asked enough questions and got 3 answers. DO NOT ask any more questions. Immediately proceed to generate the complete PRD document now. Start with: 好的，现在开始为你生成 PRD。]"

            messages.append({"role": "user", "content": user_message})

            full_response = ""
            try:
                api_key = settings.DEEPSEEK_API_KEY or settings.OPENAI_API_KEY
                client = get_http_client()
                async with client.stream(
                    "POST",
                    "https://api.deepseek.com/v1/chat/completions",
                    json={
                        "model": settings.AI_MODEL,
                        "messages": messages,
                        "temperature": settings.AI_TEMPERATURE,
                        "stream": True,
                    },
                    headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                ) as resp:
                        if resp.status_code != 200:
                            error_body = await resp.aread()
                            logger.error(f"DeepSeek API error: {resp.status_code} - " + str(error_body))
                            raise RuntimeError("API returned " + str(resp.status_code))

                        async for line in resp.aiter_lines():
                            if not line.strip():
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        full_response += content
                                        await send_event(self.websocket, "text", {"content": content})
                                except json.JSONDecodeError:
                                    continue

            except Exception as e:
                logger.error(f"Stream error: {e}", exc_info=True)
                await send_event(self.websocket, "error", {"message": str(e)})
                return

            if full_response:
                new_phase = self._detect_phase(full_response, len(self.message_history))
                if new_phase != self.phase:
                    self.phase = new_phase
                    labels = {"clarify": "追问需求", "generate": "生成 PRD"}
                    await send_event(self.websocket, "phase", {
                        "phase": new_phase, "label": labels.get(new_phase, ""), "done": False,
                    })

                await self._persist_assistant_message(full_response)
                title = self._extract_title(full_response, user_message)
                if self.conversation_id:
                    await self._update_conversation_title(title)
            else:
                logger.warning("Empty response from AI")

            await send_event(self.websocket, "phase", {"phase": "done", "label": "完成", "done": True})
            await send_event(self.websocket, "done", {})
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Agent error: {e}", exc_info=True)
            await send_event(self.websocket, "error", {"message": str(e)})
        finally:
            self.db.close()
            self.db = None

    async def _retrieve_knowledge(self, query: str) -> tuple[str, list[dict]]:
        """Pre-retrieve knowledge base content relevant to the user's query.

        Returns (formatted_context_text, structured_sources_list).
        Results are cached per session to avoid repeat retrieval.
        """
        # Session-level cache: avoid re-retrieving for repeated queries
        if not hasattr(self, '_rag_cache'):
            self._rag_cache: dict[str, tuple[str, list[dict]]] = {}
        cached = self._rag_cache.get(query)
        if cached is not None:
            return cached

        try:
            from app.agents.tools.rag_tool import _get_retrieval_service
            service = _get_retrieval_service()
            default_col = settings.rag.collection_name or "prd_templates"
            results = await service.retrieve(
                query=query, collection_name=default_col, limit=5,
            )
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
            return "", []

        lines: list[str] = []
        sources: list[dict] = []
        for i, r in enumerate(results, 1):
            fn = r.metadata.get("filename", "unknown") if isinstance(r.metadata, dict) else "unknown"
            col = r.metadata.get("collection", default_col) if isinstance(r.metadata, dict) else default_col
            content_str = str(r.content) if r.content is not None else ""
            lines.append(f"[{i}] {fn} (score: {r.score:.3f}, from: {col})")
            lines.append(content_str)
            lines.append("")
            sources.append({
                "index": i,
                "source": fn,
                "collection": col,
                "score": round(float(r.score), 3) if r.score is not None else 0,
                "preview": content_str[:120],
            })

        formatted = "以下是从知识库检索到的相关参考内容（仅供 Step 3 生成 PRD 时参考，不要因为这些内容跳过 Step 1 和 Step 2 的追问流程）：\n\n" + "\n".join(lines)
        # Cache result (limit cache to 10 entries)
        if len(self._rag_cache) < 10:
            self._rag_cache[query] = (formatted, sources)
        return formatted, sources

    async def _persist_user_message(
        self, content: str, file_ids: list[str] | None = None
    ) -> None:
        """Save user message to conversation history."""
        self.message_history.append({"role": "user", "content": content})

        if not self.db:
            return

        try:
            from app.repositories import conversation_repo
            from app.repositories import chat_file as chat_file_repo

            if not self.conversation_id:
                conv = conversation_repo.create_conversation(
                    self.db,
                    user_id=str(self.user.id) if self.user else None,
                    title="PRD Analysis",
                )
                self.conversation_id = conv.id

            msg = conversation_repo.create_message(
                self.db,
                conversation_id=self.conversation_id,
                role="user",
                content=content,
            )

            if file_ids:
                chat_file_repo.link_to_message(
                    self.db, message_id=msg.id, file_ids=file_ids
                )

            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist user message: {e}")
            self.db.rollback()

    async def _persist_assistant_message(self, content: str) -> None:
        """Save assistant message to conversation history."""
        self.message_history.append({"role": "assistant", "content": content})

        if not self.db or not self.conversation_id:
            return

        try:
            from app.repositories import conversation_repo

            conversation_repo.create_message(
                self.db,
                conversation_id=self.conversation_id,
                role="assistant",
                content=content,
                model_name=settings.AI_MODEL,
            )
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist assistant message: {e}")
            self.db.rollback()

    async def _update_conversation_title(self, title: str | None) -> None:
        """Update conversation title based on content."""
        if not title or not self.db or not self.conversation_id:
            return

        try:
            from app.repositories import conversation_repo

            conversation = conversation_repo.get_conversation_by_id(
                self.db, self.conversation_id
            )
            if conversation:
                conversation_repo.update_conversation(
                    self.db,
                    db_conversation=conversation,
                    update_data={"title": title},
                )
                self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to update title: {e}")
            self.db.rollback()

    @staticmethod
    def _extract_title(full_response: str, user_message: str) -> str:
        """Extract a short title from the conversation."""
        import re

        name_match = re.search(
            r"(?:Product Name|product name)\s*[:：]\s*(.+?)[\n\r]",
            full_response,
            re.IGNORECASE,
        )
        if name_match:
            title = name_match.group(1).strip()
            if len(title) > 100:
                title = title[:100]
            return title

        first_line = user_message.strip().split("\n")[0]
        return first_line[:100] if len(first_line) > 100 else first_line
