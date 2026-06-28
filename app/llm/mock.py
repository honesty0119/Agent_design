from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.models import LLMDecision, ToolCall


class MockLLMClient:
    """Deterministic local model substitute for demos and smoke tests."""

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMDecision:
        last = messages[-1]
        if last["role"] == "tool":
            return self._answer_from_tool(last)

        user_text = self._latest_user(messages)
        lowered = user_text.lower()
        arithmetic = re.search(r"(?:计算|算一下|calculator|calculate)\s*[:：]?\s*([0-9+\-*/().% ]+)", user_text, re.I)
        if arithmetic and arithmetic.group(1).strip():
            return self._tool("calculator", {"expression": arithmetic.group(1).strip()})

        if any(word in lowered for word in ["搜索", "查询资料", "search"]):
            query = re.sub(r"^(请)?(搜索|查询资料|search)\s*[:：]?", "", user_text, flags=re.I).strip() or user_text
            return self._tool("search", {"query": query, "limit": 3})

        todo_intent = any(word in lowered for word in ["待办", "todo"]) or bool(re.search(r"^(完成|complete)\s*\d+", lowered))
        if todo_intent:
            if any(word in lowered for word in ["列出", "查看", "list"]):
                return self._tool("todo", {"action": "list"})
            complete = re.search(r"(?:完成|complete)\s*(\d+)", lowered)
            if complete:
                return self._tool("todo", {"action": "complete", "todo_id": int(complete.group(1))})
            title = re.sub(r"^(请)?(添加|新增|创建)?\s*(待办|todo)\s*[:：]?", "", user_text, flags=re.I).strip()
            return self._tool("todo", {"action": "add", "title": title or "未命名待办"})

        return LLMDecision(
            kind="final",
            content=f"Mock 模式已收到：{user_text}\n\n可尝试：计算 12*(3+4)、搜索 Agent Runtime、添加待办 写周报。",
        )

    @staticmethod
    def _latest_user(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message["role"] == "user":
                return str(message.get("content") or "")
        return ""

    @staticmethod
    def _tool(name: str, arguments: dict[str, Any]) -> LLMDecision:
        return LLMDecision(
            kind="tool",
            tool_call=ToolCall(id=f"call_{uuid.uuid4().hex}", name=name, arguments=arguments),
        )

    @staticmethod
    def _answer_from_tool(message: dict[str, Any]) -> LLMDecision:
        try:
            result = json.loads(message.get("content") or "{}")
        except json.JSONDecodeError:
            result = {"ok": False, "error": "invalid tool result"}
        if not result.get("ok"):
            return LLMDecision(kind="final", content=f"工具执行失败：{result.get('error', '未知错误')}")
        name = message.get("name")
        data = result.get("data") or {}
        if name == "calculator":
            return LLMDecision(kind="final", content=f"计算结果：{data.get('result')}")
        if name == "search":
            lines = [f"- {item['title']}：{item['content']}" for item in data.get("results", [])]
            return LLMDecision(kind="final", content="搜索结果（Mock 数据）：\n" + "\n".join(lines))
        if name == "todo":
            if "todos" in data:
                todos = data["todos"]
                if not todos:
                    return LLMDecision(kind="final", content="当前没有待办事项。")
                lines = [f"- #{item['id']} [{'x' if item['completed'] else ' '}] {item['title']}" for item in todos]
                return LLMDecision(kind="final", content="当前待办：\n" + "\n".join(lines))
            todo = data.get("todo", {})
            state = "已完成" if todo.get("completed") else "已添加"
            return LLMDecision(kind="final", content=f"待办{state}：#{todo.get('id')} {todo.get('title')}")
        return LLMDecision(kind="final", content=json.dumps(data, ensure_ascii=False))
