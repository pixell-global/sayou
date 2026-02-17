"""Agent configuration and settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    model_config = {"env_prefix": "SAYOU_AGENT_", "env_file": ".env"}

    # Server
    host: str = "0.0.0.0"
    port: int = 9008
    debug: bool = False

    # LLM
    openai_api_key: str = ""
    chat_model: str = "gpt-4o"

    # Tavily web search (optional)
    tavily_api_key: str = ""

    # E2B Sandbox (optional)
    e2b_api_key: str = ""

    @property
    def tavily_enabled(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def sandbox_enabled(self) -> bool:
        return bool(self.e2b_api_key)


@lru_cache
def get_settings() -> AgentSettings:
    return AgentSettings()
