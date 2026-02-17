"""Agent event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    """Event emitted during agent execution.

    Types:
        status      — Agent status message ("Thinking...")
        content     — Streaming text delta
        tool_use    — Tool call requested
        tool_result — Tool execution result
        complete    — Agent finished
        error       — Error occurred
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)
