"""MCP 工具接入辅助。

与进程内 @tool 的真实差别：
- @tool：构建时把函数 import 进 Agent 进程。
- MCP：Agent 经 stdio 连到独立 server 进程，调用 tools/list 在运行时发现工具，
  再经协议发起调用。

对应知识点：MCP 解决 N×M 集成爆炸 / 工具动态发现。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

_SERVER = str(Path(__file__).with_name("mcp_server.py"))


async def discover_mcp_tools() -> list[Any]:
    """经 stdio 连接本地 FastMCP server，并列出其工具。"""
    client = MultiServerMCPClient(
        {
            "docs": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [_SERVER],
            }
        }
    )
    return await client.get_tools()


def discover_mcp_tools_sync() -> list[Any]:
    """同步封装，供脚本 / 测试调用。"""
    return asyncio.run(discover_mcp_tools())
