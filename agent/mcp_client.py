"""MCP 工具接入辅助。

与进程内 @tool 的真实差别：
- @tool：构建时把函数 import 进 Agent 进程。
- MCP：Agent 经 stdio 连到独立 server 进程，调用 tools/list 在运行时发现工具，
  再经协议发起调用。

对应知识点：MCP 解决 N×M 集成爆炸 / 工具动态发现。
可同时拉起多个 Server（docs + weather），示范「共享能力、多 Host 配置」。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Iterable, Literal

from langchain_mcp_adapters.client import MultiServerMCPClient

_DIR = Path(__file__).resolve().parent
ServerName = Literal["docs", "weather"]

_SERVER_SPECS: dict[ServerName, dict[str, Any]] = {
    "docs": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(_DIR / "mcp_server.py")],
    },
    "weather": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(_DIR / "mcp_weather_server.py")],
    },
}


def _server_config(names: Iterable[ServerName]) -> dict[str, Any]:
    chosen = list(names) or ["docs"]
    missing = [n for n in chosen if n not in _SERVER_SPECS]
    if missing:
        raise ValueError(f"unknown MCP servers: {missing}; known={list(_SERVER_SPECS)}")
    return {n: _SERVER_SPECS[n] for n in chosen}


async def discover_mcp_tools(
    *servers: ServerName,
) -> list[Any]:
    """经 stdio 连接本地 FastMCP server(s)，并列出其工具。

    默认只连 docs。示例：``await discover_mcp_tools("docs", "weather")``。
    """
    client = MultiServerMCPClient(_server_config(servers))
    return await client.get_tools()


def discover_mcp_tools_sync(*servers: ServerName) -> list[Any]:
    """同步封装，供脚本 / 测试调用。"""
    return asyncio.run(discover_mcp_tools(*servers))
