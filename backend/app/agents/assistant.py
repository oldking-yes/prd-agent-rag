
"""PydanticAI Agent wrapper (available but not the primary code path).

The main conversation flow lives in app.services.agent_session, which uses
pre-retrieval RAG → direct httpx streaming to DeepSeek.  This PydanticAI
agent is deliberately kept for comparison / experimentation / future migration:

- It defines a search_documents tool that the PydanticAI Agent would call
  at runtime if the model supports function-calling natively.
- DeepSeek Chat (the current model) does NOT support native tool/function
  calling, so the agent would need to parse tool-call instructions from the
  text stream — which is fragile and slow.
- For PRD generation, pre-retrieval (injecting relevant templates BEFORE
  generation) is actually *better* than dynamic tool calls because the
  LLM needs to see the full methodology context before it starts writing.

When to switch to this path:
- When the model supports native function calling (e.g. GPT-4, Claude).
- OR when the RAG knowledge base becomes large enough that you need
  multi-round retrieval during generation.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.agents.prompts import get_system_prompt_with_rag
from app.agents.tools import get_current_datetime
from app.agents.tools.rag_tool import search_knowledge_base
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_model(model_name: str):
    """Build model using DeepSeek via OpenAI-compatible API."""
    api_key = settings.DEEPSEEK_API_KEY or settings.OPENAI_API_KEY
    return OpenAIChatModel(
        model_name or settings.AI_MODEL,
        provider=OpenAIProvider(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
        ),
    )


@dataclass
class Deps:
    """Dependencies for the assistant agent."""

    user_id: str | None = None
    user_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PRDAgent:
    """PRD Analysis Agent wrapper for conversational AI.

    Transforms rough product ideas into structured PRDs using RAG-enhanced analysis.
    """

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ):
        self.model_name = model_name or settings.AI_MODEL
        self.temperature = temperature if temperature is not None else settings.AI_TEMPERATURE
        self.system_prompt = system_prompt or get_system_prompt_with_rag()
        self._agent: Agent[Deps, str] | None = None

    def _create_agent(self) -> Agent[Deps, str]:
        """Create and configure the PydanticAI agent."""
        model = _build_model(self.model_name)

        model_settings: ModelSettings = ModelSettings(temperature=self.temperature)

        agent = Agent[Deps, str](
            model=model,
            model_settings=model_settings,
            system_prompt=self.system_prompt,
        )

        self._register_tools(agent)
        return agent

    def _register_tools(self, agent: Agent[Deps, str]) -> None:
        """Register all tools on the agent."""

        @agent.tool_plain
        def current_datetime() -> dict[str, str]:
            """Get the current date and time."""
            return get_current_datetime()

        @agent.tool
        async def search_documents(
            ctx: RunContext[Deps], query: str, top_k: int = 5
        ) -> str:
            """Search the knowledge base for relevant PRD templates, product methodologies, and competitive analysis frameworks.

            Always use this tool before analyzing a product idea to find relevant templates and frameworks.

            Args:
                query: The search query string.
                top_k: Number of top results to retrieve (default: 5).

            Returns:
                Formatted string with search results including content and scores.
            """
            try:
                return await search_knowledge_base(query=query, top_k=top_k)
            except Exception as e:
                raise ModelRetry("Knowledge base temporarily unavailable, please try again.") from e

    @staticmethod
    def _build_model_history(
        history: list[dict[str, str]] | None,
    ) -> list[Any]:
        from pydantic_ai.messages import (
            ModelRequest,
            ModelResponse,
            SystemPromptPart,
            TextPart,
            UserPromptPart,
        )

        model_history: list[ModelRequest | ModelResponse] = []
        for msg in history or []:
            if msg["role"] == "user":
                model_history.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
            elif msg["role"] == "assistant":
                model_history.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
            elif msg["role"] == "system":
                model_history.append(ModelRequest(parts=[SystemPromptPart(content=msg["content"])]))
        return model_history

    @property
    def agent(self) -> Agent[Deps, str]:
        """Get or create the agent instance."""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    async def run(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        deps: Deps | None = None,
    ) -> tuple[str, list[Any], Deps]:
        """Run agent and return the output along with tool call events."""
        agent_deps = deps if deps is not None else Deps()

        logger.info(f"Running PRD agent with user input: {user_input[:100]}...")
        result = await self.agent.run(
            user_input,
            deps=agent_deps,
            message_history=self._build_model_history(history),
        )

        tool_events: list[Any] = []
        for message in result.all_messages():
            if hasattr(message, "parts"):
                for part in message.parts:
                    if hasattr(part, "tool_name"):
                        tool_events.append(part)

        logger.info(f"Agent run complete. Output length: {len(result.output)} chars")
        return result.output, tool_events, agent_deps

    async def iter(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        deps: Deps | None = None,
    ) -> Any:
        """Stream agent execution with full event access."""
        agent_deps = deps if deps is not None else Deps()

        async with self.agent.iter(
            user_input,
            deps=agent_deps,
            message_history=self._build_model_history(history),
        ) as run:
            async for event in run:
                yield event


def get_agent(
    model_name: str | None = None,
    temperature: float | None = None,
) -> PRDAgent:
    """Factory function to create a PRDAgent."""
    return PRDAgent(
        model_name=model_name,
        temperature=temperature,
    )
