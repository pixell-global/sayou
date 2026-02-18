"""Memory adapter registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmarks.runner.adapter import MemoryAdapter


def get_adapter(name: str, **kwargs) -> MemoryAdapter:
    """Instantiate an adapter by name."""
    registry = _build_registry()
    if name not in registry:
        available = [n for n, cls in registry.items() if cls.available()]
        raise ValueError(
            f"Unknown adapter: {name!r}. Available: {', '.join(available)}"
        )
    cls = registry[name]
    if not cls.available():
        raise RuntimeError(
            f"Adapter {name!r} is not available (missing dependencies). "
            f"Check that required packages are installed."
        )
    return cls(**kwargs)


def list_adapters() -> list[str]:
    """Return names of all available adapters."""
    registry = _build_registry()
    return [name for name, cls in registry.items() if cls.available()]


def _build_registry() -> dict[str, type]:
    from benchmarks.runner.adapters.no_memory import NoMemoryAdapter
    from benchmarks.runner.adapters.oracle import OracleAdapter
    from benchmarks.runner.adapters.sayou_adapter import SayouAdapter
    from benchmarks.runner.adapters.chromadb_adapter import ChromaDBAdapter
    from benchmarks.runner.adapters.mem0_adapter import Mem0Adapter
    from benchmarks.runner.adapters.zep_adapter import ZepAdapter

    return {
        "no-memory": NoMemoryAdapter,
        "oracle": OracleAdapter,
        "sayou": SayouAdapter,
        "chromadb": ChromaDBAdapter,
        "mem0": Mem0Adapter,
        "zep": ZepAdapter,
    }
