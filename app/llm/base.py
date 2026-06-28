from __future__ import annotations

from typing import Any, Protocol

from app.models import LLMDecision


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMDecision:
        ...
