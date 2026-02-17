"""Python executor — runs Python code in E2B sandbox."""

from __future__ import annotations

from typing import Any

from sayou.agent.sandbox.manager import SandboxManager
from sayou.agent.tools.executors.base import BaseExecutor, ToolResult


class PythonExecutor(BaseExecutor):
    """Execute Python code in an isolated E2B sandbox."""

    def __init__(self, sandbox_manager: SandboxManager, session_id: str):
        self._sandbox = sandbox_manager
        self._session_id = session_id

    @property
    def name(self) -> str:
        return "execute_python"

    @property
    def description(self) -> str:
        return "Execute Python code in an isolated sandbox. Use print() to produce output."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute.",
                },
            },
            "required": ["code"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        code = kwargs.get("code", "")
        if not code:
            return ToolResult.error_result("Code is required.")

        result = await self._sandbox.execute_code(self._session_id, code)

        if result["error"]:
            output = ""
            if result["stdout"]:
                output += f"stdout:\n{result['stdout']}\n"
            if result["stderr"]:
                output += f"stderr:\n{result['stderr']}\n"
            return ToolResult(
                success=False,
                output=output,
                error=result["error"],
                recoverable=True,
            )

        output_parts = []
        if result["stdout"]:
            output_parts.append(result["stdout"])
        if result["stderr"]:
            output_parts.append(f"stderr:\n{result['stderr']}")
        return ToolResult.success_result("\n".join(output_parts) or "(no output)")
