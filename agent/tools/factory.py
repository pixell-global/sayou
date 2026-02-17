"""Tool factory — creates tools based on configuration."""

from __future__ import annotations

from sayou.workspace import Workspace

from sayou.agent.sandbox.manager import SandboxManager
from sayou.agent.tools.executors.base import BaseExecutor
from sayou.agent.tools.executors.workspace_list import WorkspaceListExecutor
from sayou.agent.tools.executors.workspace_read import WorkspaceReadExecutor
from sayou.agent.tools.executors.workspace_search import WorkspaceSearchExecutor
from sayou.agent.tools.executors.workspace_write import WorkspaceWriteExecutor


class ToolFactory:
    """Creates tool executors for a given session."""

    def __init__(
        self,
        sandbox_manager: SandboxManager | None = None,
        sandbox_enabled: bool = False,
        tavily_api_key: str | None = None,
    ):
        self._sandbox_manager = sandbox_manager
        self._sandbox_enabled = sandbox_enabled and sandbox_manager is not None
        self._tavily_api_key = tavily_api_key

    def create_tools(self, workspace: Workspace, session_id: str) -> list[BaseExecutor]:
        tools: list[BaseExecutor] = [
            WorkspaceSearchExecutor(workspace),
            WorkspaceReadExecutor(workspace),
            WorkspaceListExecutor(workspace),
            WorkspaceWriteExecutor(workspace),
        ]

        if self._tavily_api_key:
            from sayou.agent.tools.executors.web_search import WebSearchExecutor

            tools.append(WebSearchExecutor(self._tavily_api_key))

        if self._sandbox_enabled and self._sandbox_manager:
            from sayou.agent.tools.executors.bash import BashExecutor
            from sayou.agent.tools.executors.python_exec import PythonExecutor

            tools.append(BashExecutor(self._sandbox_manager, session_id))
            tools.append(PythonExecutor(self._sandbox_manager, session_id))

        return tools
