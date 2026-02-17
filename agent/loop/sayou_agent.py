"""Core agent loop — multi-turn streaming with tool execution."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sayou.workspace import Workspace

from sayou.agent.loop.events import AgentEvent
from sayou.agent.loop.llm_provider import LLMProvider
from sayou.agent.tools.factory import ToolFactory

logger = logging.getLogger(__name__)


class SayouAgent:
    """Multi-turn agent with workspace tools and optional sandbox."""

    def __init__(
        self,
        llm: LLMProvider,
        tool_factory: ToolFactory,
        max_turns: int = 10,
    ):
        self.llm = llm
        self.tool_factory = tool_factory
        self.max_turns = max_turns

    async def run(
        self,
        session_id: str,
        user_message: str,
        history: list[dict[str, Any]],
        workspace: Workspace,
        system_prompt: str,
    ) -> AsyncIterator[AgentEvent]:
        tools = self.tool_factory.create_tools(workspace, session_id)
        tool_schemas = [t.as_tool_schema() for t in tools]
        tool_map = {t.name: t for t in tools}

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_message},
        ]

        for turn in range(self.max_turns):
            logger.info(f"Agent turn {turn + 1}/{self.max_turns}")
            yield AgentEvent(type="status", data={"message": "Thinking..."})

            content_parts: list[str] = []
            tool_calls: list[dict[str, str]] = []
            error_occurred = False

            try:
                async for chunk in self.llm.stream_with_tools(
                    messages, tool_schemas if tools else None
                ):
                    if chunk.type == "content" and chunk.content:
                        content_parts.append(chunk.content)
                        yield AgentEvent(type="content", data={"text": chunk.content})

                    elif chunk.type == "tool_call":
                        tool_calls.append({
                            "id": chunk.tool_call_id or f"call_{uuid.uuid4().hex[:12]}",
                            "name": chunk.tool_name or "",
                            "arguments": chunk.tool_arguments or "{}",
                        })

                    elif chunk.type == "error":
                        yield AgentEvent(type="error", data={"message": chunk.error})
                        error_occurred = True
                        break

            except Exception as e:
                logger.error(f"Error in agent turn: {e}")
                yield AgentEvent(type="error", data={"message": str(e)})
                return

            if error_occurred:
                return

            full_content = "".join(content_parts)

            # No tool calls — agent is done
            if not tool_calls:
                yield AgentEvent(type="complete", data={"content": full_content})
                return

            # Add assistant message with tool calls
            messages.append(
                self.llm.format_assistant_message_with_tool_calls(full_content, tool_calls)
            )

            # Execute each tool call
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args_str = tc["arguments"]

                yield AgentEvent(
                    type="tool_use",
                    data={
                        "name": tool_name,
                        "arguments": tool_args_str,
                        "call_id": tc["id"],
                    },
                )

                # Parse arguments
                try:
                    tool_args = json.loads(tool_args_str) if tool_args_str else {}
                except json.JSONDecodeError as e:
                    result_content = f"Error: Invalid arguments — {e}"
                    yield AgentEvent(
                        type="tool_result",
                        data={"name": tool_name, "result": result_content, "call_id": tc["id"]},
                    )
                    messages.append(self.llm.format_tool_result_message(tc["id"], result_content))
                    continue

                # Execute
                executor = tool_map.get(tool_name)
                if executor:
                    try:
                        result = await executor.execute(**tool_args)
                        result_content = result.to_content()
                    except Exception as e:
                        logger.error(f"Tool {tool_name} error: {e}")
                        result_content = f"Error: Failed to execute {tool_name}. Please try again."
                else:
                    result_content = f"Error: Unknown tool '{tool_name}'."

                yield AgentEvent(
                    type="tool_result",
                    data={"name": tool_name, "result": result_content, "call_id": tc["id"]},
                )
                messages.append(self.llm.format_tool_result_message(tc["id"], result_content))

        # Max turns reached
        yield AgentEvent(
            type="complete",
            data={"content": "I've reached the maximum number of turns. Please continue if you need more help."},
        )
