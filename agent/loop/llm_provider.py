"""OpenAI LLM provider with streaming and tool call support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 5, 15]


@dataclass
class LLMChunk:
    """Chunk from LLM streaming response."""

    type: str  # "content", "tool_call", "tool_call_delta", "done", "error"
    content: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_arguments: str | None = None
    error: str | None = None


class LLMProvider:
    """OpenAI streaming LLM with tool call accumulation."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMChunk]:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                async for chunk in self._stream(messages, tools, max_tokens):
                    yield chunk
                return
            except Exception as e:
                last_error = e
                if self._is_rate_limit(e) and attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(f"Rate limited, retry in {delay}s (attempt {attempt + 1})")
                    await asyncio.sleep(delay)
                    continue
                raise

        if last_error:
            raise last_error

    def _is_rate_limit(self, error: Exception) -> bool:
        err = str(error).lower()
        return any(x in err for x in ["rate", "429", "too many requests"])

    async def _stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> AsyncIterator[LLMChunk]:
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await self.client.chat.completions.create(**kwargs)

            tool_calls: dict[int, dict[str, str]] = {}

            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                if delta.content:
                    yield LLMChunk(type="content", content=delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["arguments"] += tc.function.arguments

                finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
                if finish_reason == "tool_calls":
                    for _idx, tc in sorted(tool_calls.items()):
                        yield LLMChunk(
                            type="tool_call",
                            tool_call_id=tc["id"],
                            tool_name=tc["name"],
                            tool_arguments=tc["arguments"],
                        )

            yield LLMChunk(type="done")

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            yield LLMChunk(type="error", error=str(e))

    def format_tool_result_message(self, tool_call_id: str, result: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    def format_assistant_message_with_tool_calls(
        self,
        content: str | None,
        tool_calls: list[dict[str, str]],
    ) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in tool_calls
            ],
        }
        return msg
