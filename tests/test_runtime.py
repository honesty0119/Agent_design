from __future__ import annotations

import asyncio

from app.config import DEFAULT_SYSTEM_PROMPT
from app.context import ContextBuilder
from app.database import SessionStore
from app.llm.mock import MockLLMClient
from app.models import LLMDecision, ToolCall
from app.runtime import AgentRuntime
from app.tools import CalculatorTool, MockSearchTool, TodoTool, ToolRegistry
from tests.helpers import ScriptedLLM


def make_runtime(tmp_path, llm=None, max_steps=8):
    store = SessionStore(str(tmp_path / "agent.db"))
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(MockSearchTool())
    registry.register(TodoTool())
    context = ContextBuilder(store, DEFAULT_SYSTEM_PROMPT, max_context_chars=4000, recent_messages=6)
    return AgentRuntime(store, llm or MockLLMClient(), registry, context, max_steps=max_steps, tool_timeout_seconds=1)


def test_tool_loop_returns_calculation(tmp_path):
    runtime = make_runtime(tmp_path)
    session = runtime.store.create_session()
    result = asyncio.run(runtime.chat(session["id"], "计算 12*(3+4)"))
    assert "84" in result.answer
    messages = runtime.store.list_messages(session["id"])
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[2]["name"] == "calculator"


def test_sessions_are_isolated(tmp_path):
    runtime = make_runtime(tmp_path)
    first = runtime.store.create_session("first")
    second = runtime.store.create_session("second")
    asyncio.run(runtime.chat(first["id"], "添加待办 写周报"))
    asyncio.run(runtime.chat(second["id"], "列出待办"))
    assert len(runtime.store.list_todos(first["id"])) == 1
    assert runtime.store.list_todos(second["id"]) == []
    assert "没有待办" in runtime.store.list_messages(second["id"])[-1]["content"]


def test_repeated_tool_call_is_stopped(tmp_path):
    repeated = LLMDecision(kind="tool", tool_call=ToolCall(id="same", name="calculator", arguments={"expression": "1+1"}))
    runtime = make_runtime(tmp_path, ScriptedLLM([repeated, repeated, repeated]), max_steps=6)
    session = runtime.store.create_session()
    result = asyncio.run(runtime.chat(session["id"], "loop"))
    assert "重复工具调用" in result.answer
    assert runtime.store.get_session(session["id"])["status"] == "failed"


def test_max_steps_guard(tmp_path):
    calls = [LLMDecision(kind="tool", tool_call=ToolCall(id=str(i), name="calculator", arguments={"expression": f"{i}+1"})) for i in range(3)]
    runtime = make_runtime(tmp_path, ScriptedLLM(calls), max_steps=3)
    session = runtime.store.create_session()
    result = asyncio.run(runtime.chat(session["id"], "keep going"))
    assert "最大执行轮数" in result.answer
    assert result.steps == 3
