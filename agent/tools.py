"""Agent 可调用的工具。

设计要点：
- 用本模块的 `@tool` 装饰：内部仍是 LangChain `@tool`，并**自动注册**进仓库。
- `get_tools()` 返回已注册列表；`graph.build_agent` 默认用它，不必再改全局 TOOLS。
- 模型从不自己执行工具，只发出结构化调用请求；真正执行在图里的 ToolNode。
- 绝不要把用户原文丢进 eval/exec。这里用 ast + 白名单语法做安全求值。
"""

from __future__ import annotations

import ast
import json
import operator
from typing import Any, Callable

from langchain_core.tools import BaseTool
from langchain_core.tools import tool as langchain_tool

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# name -> BaseTool；由 @tool / register_tool 写入
_REGISTRY: dict[str, BaseTool] = {}


def register_tool(tool_obj: BaseTool) -> BaseTool:
    """显式注册一个已构造好的 BaseTool（例如来自 MCP 适配后再并入本地仓）。"""
    _REGISTRY[tool_obj.name] = tool_obj
    return tool_obj


def get_tools() -> list[BaseTool]:
    """当前已注册的本地工具（稳定按 name 排序）。"""
    return sorted(_REGISTRY.values(), key=lambda t: t.name)


def clear_tools() -> None:
    """仅供测试重置注册表。"""
    _REGISTRY.clear()


def tool(fn: Callable[..., Any] | None = None, **kwargs: Any):
    """LangChain `@tool` + 自动 `register_tool`。

    用法与官方一致：
        @tool
        def foo(...): ...
    """

    def deco(f: Callable[..., Any]) -> BaseTool:
        built = langchain_tool(**kwargs)(f) if kwargs else langchain_tool(f)
        return register_tool(built)

    if fn is not None:
        return deco(fn)
    return deco


def _safe_eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](
            _safe_eval(node.left), _safe_eval(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_safe_eval(node.operand))
    raise ValueError("invalid expression")


@tool
def calculator(expression: str) -> str:
    """安全求值算术表达式。仅支持 + - * / ** % 与数字。

    Args:
        expression: 算术表达式，例如 "2 * (3 + 4)"。
    """
    try:
        tree = ast.parse(expression, mode="eval")
        value = _safe_eval(tree)
        return str(int(value) if float(value).is_integer() else round(value, 6))
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as exc:
        return f"error: invalid expression ({exc})"


# 离线假数据：测试与演示不依赖不稳定的外部天气 API。
_WEATHER_FIXTURE = {
    "北京": {"temp_c": 21, "condition": "晴"},
    "上海": {"temp_c": 26, "condition": "多云"},
}


@tool
def get_weather(city: str) -> str:
    """查询某城市今日天气。离线演示数据：北京 / 上海。

    Args:
        city: 中文城市名，例如 "北京"。
    """
    data = _WEATHER_FIXTURE.get(city, {"temp_c": 20, "condition": "未知"})
    return json.dumps({"city": city, **data}, ensure_ascii=False)
