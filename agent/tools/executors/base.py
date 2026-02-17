"""Base executor interface for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result from tool execution."""

    success: bool
    output: str
    error: str | None = None
    error_code: str | None = None
    recoverable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_content(self) -> str:
        if self.success:
            return self.output
        return f"Error: {self.error}"

    @classmethod
    def success_result(cls, output: str, **metadata: Any) -> ToolResult:
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def error_result(
        cls,
        error: str,
        error_code: str | None = None,
        recoverable: bool = False,
        **metadata: Any,
    ) -> ToolResult:
        return cls(
            success=False,
            output="",
            error=error,
            error_code=error_code,
            recoverable=recoverable,
            metadata=metadata,
        )


class BaseExecutor(ABC):
    """Base class for tool executors."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        ...

    def as_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
