
"""Agent session management for WebSocket-based PRD analysis.

Handles the lifecycle of a single agent conversation session:
- Message processing and streaming via PydanticAI agent.iter()
- Tool-augmented RAG (LLM calls search_documents when needed)
- Conversation persistence
- Fallback to direct DeepSeek API if agent path fails
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import WebSocket
from pydantic_ai import UsageLimits

from app.agents.assistant import PRDAgent, Deps
from app.core.config import settings
from app.db.models.user import User
from app.services.agent import send_event, build_message_history
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
)

logger = logging.getLogger(__name__)

# Token budget per session
MAX_HISTORY_MESSAGES = 20  # Keep last N messages to control context size
TOKEN_LIMITS = UsageLimits(
    request_limit=20,             # Max LLM requests per turn
    total_tokens_limit=80000,     # Max total tokens per turn
)


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
            await self._persist_user_message(user_message, file_ids)
            await send_event(self.websocket, "status", {"status": "thinking"})
            await send_event(self.websocket, "status", {"status": "generating"})

            # Pre-retrieve RAG knowledge and inject into system prompt
            agent = PRDAgent()
            base_prompt = agent.system_prompt or "你是一位产品经理，帮助用户分析产品需求并生成 PRD。"
            rag_context, rag_sources = await self._retrieve_knowledge(user_message)

            if rag_context:
                enhanced_prompt = base_prompt + "\n\n---\n" + rag_context
                await send_event(self.websocket, "rag_context", {"sources": rag_sources})
                await send_event(self.websocket, "phase", {"phase": "understand", "label": "理解需求", "done": False})
            else:
                enhanced_prompt = base_prompt

            # Trim history to control token usage (keep last N messages)
            trimmed_history = self.message_history[-MAX_HISTORY_MESSAGES:] if len(self.message_history) > MAX_HISTORY_MESSAGES else self.message_history
            model_history = build_message_history(trimmed_history)

            # Run via PydanticAI agent — LLM can call search_documents tool
            deps = Deps(user_id=str(self.user.id) if self.user else None)
            full_response = ""

            try:
                logger.info("Starting agent.iter() with tools enabled")
                collected_tool_names: list[str] = []
                async with agent.agent.iter(
                    user_message,
                    deps=deps,
                    message_history=model_history,
                    instructions=enhanced_prompt,
                    usage_limits=TOKEN_LIMITS,
                ) as run:
                    async for node in run:
                        if agent.agent.is_model_request_node(node):
                            async with node.stream(run.ctx) as stream:
                                async for text in stream.stream_text(delta=True):
                                    full_response += text
                                    await send_event(self.websocket, "text", {"content": text})
                        elif agent.agent.is_call_tools_node(node):
                            # Collect tool names from model response parts
                            for part in node.model_response.parts:
                                if hasattr(part, 'tool_name'):
                                    collected_tool_names.append(part.tool_name)
                logger.info("agent.iter() completed, response length=%d", len(full_response))

                # Log token usage
                usage = run.usage
                logger.info(
                    "token_usage: input=%d output=%d total=%d requests=%d tools=%d",
                    usage.input_tokens, usage.output_tokens,
                    usage.total_tokens, usage.requests, usage.tool_calls,
                )

                # Persist to UsageService
                try:
                    from app.db.session import SessionLocal as SL
                    from app.services.usage import UsageService
                    udb = SL()
                    UsageService(udb).record(
                        session_id=self.conversation_id,
                        model=settings.AI_MODEL,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cached_tokens=usage.cache_read_tokens,
                        tool_calls=usage.tool_calls,
                        tool_names=collected_tool_names,
                        response_time_ms=0,
                    )
                    udb.close()
                    logger.info("Usage recorded: %d tokens, tools=%s", usage.total_tokens, collected_tool_names)
                except Exception as e:
                    logger.error("FAILED to record usage: %s", e, exc_info=True)
                # Send usage stats to frontend
                await send_event(self.websocket, "usage", {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "requests": usage.requests,
                    "tool_calls": usage.tool_calls,
                })
            except Exception as agent_err:
                logger.warning("agent.iter() failed (%s), falling back to direct API", agent_err)
                full_response = await self._fallback_direct_call(
                    enhanced_prompt, self.message_history, user_message,
                )
                # Send the full response as a single chunk (no streaming in fallback)
                if full_response:
                    await send_event(self.websocket, "text", {"content": full_response})

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

        Searches 'prd_core' collection (always) and 'prd_enhanced' collection
        (if enabled in state file). Returns (formatted_context_text, structured_sources_list).
        """
        try:
            from app.agents.tools.rag_tool import _get_retrieval_service
            from app.core.config import settings as cfg
            service = _get_retrieval_service()

            # Always search core, conditionally search enhanced
            collections = ["prd_core"]

            # Load enabled state from JSON file
            state_file = Path(cfg.CHROMA_PERSIST_DIR) / "enabled_collections.json"
            try:
                enabled = json.loads(state_file.read_text()) if state_file.exists() else {}
                if enabled.get("prd_enhanced"):
                    collections.append("prd_enhanced")
            except Exception:
                pass

            if len(collections) > 1:
                results = await service.retrieve_multi(
                    query=query, collection_names=collections, limit=5,
                )
            else:
                results = await service.retrieve(
                    query=query, collection_name=collections[0], limit=5,
                )
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
            return "", []

        lines: list[str] = []
        sources: list[dict] = []
        for i, r in enumerate(results, 1):
            fn = r.metadata.get("filename", "unknown") if isinstance(r.metadata, dict) else "unknown"
            col = r.metadata.get("collection", collections[0]) if isinstance(r.metadata, dict) else collections[0]
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
        return formatted, sources

    async def _fallback_direct_call(
        self, system_prompt: str, history: list[dict], user_message: str,
    ) -> str:
        """Fallback: stream directly from DeepSeek API without tool calling."""
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        api_key = settings.DEEPSEEK_API_KEY or settings.OPENAI_API_KEY
        full_response = ""
        async with httpx.AsyncClient(timeout=120.0) as client:
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
                    logger.error("DeepSeek API error: %s - %s", resp.status_code, error_body)
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
                        except json.JSONDecodeError:
                            continue
        return full_response

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
