from __future__ import annotations

import asyncio

from app.database import SessionStore
from app.tools.base import ToolContext
from app.tools.builtin import CalculatorTool


def test_calculator_accepts_arithmetic(tmp_path):
    store = SessionStore(str(tmp_path / "test.db"))
    session = store.create_session()
    context = ToolContext(session["id"], "trace", store)
    result = asyncio.run(CalculatorTool().execute({"expression": "(12 + 3) * 4"}, context))
    assert result.ok is True
    assert result.data["result"] == 60


def test_calculator_rejects_code_execution(tmp_path):
    store = SessionStore(str(tmp_path / "test.db"))
    session = store.create_session()
    context = ToolContext(session["id"], "trace", store)
    try:
        asyncio.run(CalculatorTool().execute({"expression": "__import__('os').system('echo bad')"}, context))
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unsafe expression was accepted")


def test_registry_validates_schema(tmp_path):
    from app.tools.registry import ToolRegistry

    store = SessionStore(str(tmp_path / "schema.db"))
    session = store.create_session()
    context = ToolContext(session["id"], "trace", store)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    result = asyncio.run(registry.execute("calculator", {"wrong": "1+1"}, context, 1))
    assert result.ok is False
    assert "missing required argument" in result.error
