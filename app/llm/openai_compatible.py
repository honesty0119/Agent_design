from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import httpx

from app.llm.base import LLMError
from app.models import LLMDecision, ToolCall


class OpenAICompatibleClient:
    """Client for OpenAI-compatible /chat/completions endpoints."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: float = 60.0, max_retries: int = 2) -> None:
        if not api_key:
            raise ValueError("AGENT_LLM_API_KEY is required in openai mode")
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMDecision:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.1}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        retryable_statuses = {429, 500, 502, 503, 504}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(self.endpoint, headers=headers, json=payload)
                    response.raise_for_status()
                    return self._parse(response.json())
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code not in retryable_statuses:
                        raise LLMError(f"model returned HTTP {exc.response.status_code}") from exc
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    # A malformed structured response is often transient. Retry
                    # once through the same bounded retry mechanism.
                    last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
        raise LLMError(f"model request failed after retries: {type(last_error).__name__}")

    @staticmethod
    def _parse(payload: dict[str, Any]) -> LLMDecision:
        message = payload["choices"][0]["message"]
        usage = payload.get("usage") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            raw = tool_calls[0]
            function = raw["function"]
            raw_arguments = function.get("arguments") or "{}"
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be a JSON object")
            return LLMDecision(
                kind="tool",
                content=message.get("content") or "",
                tool_call=ToolCall(id=raw.get("id") or f"call_{uuid.uuid4().hex}", name=function["name"], arguments=arguments),
                usage=usage,
            )
        return LLMDecision(kind="final", content=message.get("content") or "", usage=usage)
