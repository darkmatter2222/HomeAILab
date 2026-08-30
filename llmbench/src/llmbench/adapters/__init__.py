"""Engine adapters (goal.md §5)."""

from .base import EngineAdapter, EndpointMeta
from .vllm import VllmAdapter
from .llamacpp import LlamaCppAdapter
from .generic import GenericAdapter

# Registration table (priority order).  Add new engines here.
ADAPTERS: list[type[EngineAdapter]] = [VllmAdapter, LlamaCppAdapter]


def get_adapter(engine_name: str) -> EngineAdapter:
    table = {a.name: a for a in ADAPTERS}
    if engine_name in table:
        return table[engine_name]()
    return GenericAdapter()


__all__ = [
    "EngineAdapter",
    "EndpointMeta",
    "VllmAdapter",
    "LlamaCppAdapter",
    "GenericAdapter",
    "ADAPTERS",
    "get_adapter",
]
