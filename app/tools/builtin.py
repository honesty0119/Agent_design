from __future__ import annotations

import ast
import operator
from typing import Any

from app.models import ToolResult
from app.tools.base import Tool, ToolContext


class CalculatorTool(Tool):
    name = "calculator"
    description = "Safely evaluate a basic arithmetic expression."
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "Arithmetic expression, for example (12+3)*4."}},
        "required": ["expression"],
        "additionalProperties": False,
    }
    _binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
    _unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        expression = arguments.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("expression must be a non-empty string")
        if len(expression) > 200:
            raise ValueError("expression is too long")
        value = self._evaluate(ast.parse(expression, mode="eval").body, depth=0)
        return ToolResult(ok=True, data={"expression": expression, "result": value})

    def _evaluate(self, node: ast.AST, depth: int) -> int | float:
        if depth > 20:
            raise ValueError("expression is too complex")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("only numeric constants are allowed")
            if abs(node.value) > 1e100:
                raise ValueError("number is too large")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self._binary:
            left = self._evaluate(node.left, depth + 1)
            right = self._evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("exponent is too large")
            return self._binary[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in self._unary:
            return self._unary[type(node.op)](self._evaluate(node.operand, depth + 1))
        raise ValueError("unsupported expression")


class MockSearchTool(Tool):
    name = "search"
    description = "Search a small local knowledge base. This deterministic mock can be replaced by a real provider."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    _documents = [
        {"title": "Agent Runtime", "content": "An Agent Runtime coordinates model calls, tool execution, session state, context construction and observability."},
        {"title": "Context compression", "content": "Keep recent turns verbatim and summarize older facts, decisions, pending work and important tool results."},
        {"title": "Session isolation", "content": "Each chat window should use a distinct session identifier and an independent ordered message history."},
        {"title": "Tool safety", "content": "Validate tool arguments, enforce timeouts and return structured errors rather than leaking exceptions."},
    ]

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        query = arguments.get("query")
        limit = arguments.get("limit", 3)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer")
        limit = max(1, min(limit, 5))
        tokens = {token.lower() for token in query.split() if token}
        def score(document: dict[str, str]) -> int:
            text = f"{document['title']} {document['content']}".lower()
            return sum(token in text for token in tokens)
        ranked = sorted(self._documents, key=score, reverse=True)
        results = [item for item in ranked if score(item) > 0][:limit]
        if not results:
            results = ranked[:min(limit, 2)]
        return ToolResult(ok=True, data={"query": query, "results": results, "mock": True})


class TodoTool(Tool):
    name = "todo"
    description = "Add, list or complete todo items in the current session."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "complete"]},
            "title": {"type": "string", "description": "Required when action is add."},
            "due_time": {"type": ["string", "null"], "description": "Optional ISO-8601 due time."},
            "todo_id": {"type": "integer", "description": "Required when action is complete."},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        action = arguments.get("action")
        if action == "add":
            title = arguments.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("title is required for action=add")
            todo = context.store.add_todo(context.session_id, title.strip(), arguments.get("due_time"))
            return ToolResult(ok=True, data={"todo": todo})
        if action == "list":
            return ToolResult(ok=True, data={"todos": context.store.list_todos(context.session_id)})
        if action == "complete":
            todo_id = arguments.get("todo_id")
            if not isinstance(todo_id, int) or isinstance(todo_id, bool):
                raise ValueError("todo_id is required for action=complete")
            todo = context.store.complete_todo(context.session_id, todo_id)
            return ToolResult(ok=True, data={"todo": todo})
        raise ValueError("action must be add, list or complete")
