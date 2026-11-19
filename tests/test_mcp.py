"""MCP 接入测试。"""

import asyncio

import pytest

from agent.mcp_client import discover_mcp_tools, discover_mcp_tools_sync


def test_mcp_server_discovery():
    """Agent 在运行时从独立 server 进程发现工具。"""
    tools = discover_mcp_tools_sync("docs")
    names = {t.name for t in tools}
    assert "lookup_docs" in names, f"discovered: {names}"


def test_weather_mcp_server_discovery_and_fixture_align():
    """共享 Weather MCP：与本地 weather_fixture 同源。"""
    from agent.weather_fixture import lookup_weather

    tools = discover_mcp_tools_sync("weather")
    names = {t.name for t in tools}
    assert "get_weather" in names, f"discovered: {names}"
    weather = next(t for t in tools if t.name == "get_weather")
    result = asyncio.run(weather.ainvoke({"city": "北京"}))
    text = "".join(
        block.get("text", "")
        for block in result
        if isinstance(block, dict) and block.get("type") == "text"
    )
    assert text == lookup_weather("北京")


def test_multi_server_discovery():
    tools = discover_mcp_tools_sync("docs", "weather")
    names = {t.name for t in tools}
    assert {"lookup_docs", "get_weather"} <= names


def test_mcp_tool_execution():
    """MCP 适配后的工具仅支持异步——生产里常见坑。

    langchain_mcp_adapters 把 MCP 工具转成只有 coroutine 的 StructuredTool；
    .invoke() 会抛 NotImplementedError。必须 .ainvoke()，因此 Agent 入口也要 async。
    """
    tools = discover_mcp_tools_sync("docs")
    lookup = next(t for t in tools if t.name == "lookup_docs")
    result = asyncio.run(lookup.ainvoke({"topic": "refund"}))
    # MCP 适配器返回内容块列表，不是纯字符串。
    text = "".join(
        block.get("text", "")
        for block in result
        if isinstance(block, dict) and block.get("type") == "text"
    )
    assert "7 天" in text and "退款" in text


def test_mcp_policy_aligned_with_snippets():
    from agent.policy_snippets import POLICY_BY_TOPIC

    tools = discover_mcp_tools_sync("docs")
    lookup = next(t for t in tools if t.name == "lookup_docs")
    for topic, expected in POLICY_BY_TOPIC.items():
        result = asyncio.run(lookup.ainvoke({"topic": topic}))
        text = "".join(
            block.get("text", "")
            for block in result
            if isinstance(block, dict) and block.get("type") == "text"
        )
        assert text == expected
