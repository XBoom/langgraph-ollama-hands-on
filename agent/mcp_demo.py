"""支持 MCP 的 Agent 演示：进程内工具 + 远程 MCP（政策 + 天气）同图。

运行：
    poetry run python -m agent.mcp_demo

- docs Server：lookup_docs（政策键值）
- weather Server：get_weather（与本地 fixture 同源）
- 本地去掉 get_weather，避免与 MCP 工具同名冲突；计算器仍用进程内 @tool

说明：Function Calling = 模型发 tool_calls；MCP = Host↔Server 发现/调用。
"""

from __future__ import annotations

import asyncio

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from agent.graph import DEFAULT_SYSTEM_PROMPT, compose_system_prompt, make_trace_middleware
from agent.mcp_client import discover_mcp_tools
from agent.tools import get_tools

TRACE = "traces/mcp_agent.jsonl"


async def main() -> None:
    remote_tools = await discover_mcp_tools("docs", "weather")
    # 天气走 MCP；本地只留 calculator / retrieve_policy 等，避免 get_weather 重名
    local_tools = [t for t in get_tools() if t.name != "get_weather"]
    all_tools = [*local_tools, *remote_tools]
    print(
        f"MCP servers=docs+weather tools={[t.name for t in remote_tools]}; "
        f"local={[t.name for t in local_tools]}"
    )

    llm = ChatOllama(model="qwen2.5:14b", temperature=0, base_url="http://127.0.0.1:11434")
    base = (
        DEFAULT_SYSTEM_PROMPT
        + " 查政策用 lookup_docs（topic: refund/shipping/warranty）；"
        + "查天气用 get_weather；计算用 calculator。"
    )
    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=compose_system_prompt(base, all_tools),
        middleware=make_trace_middleware(TRACE),
    )
    cfg = {"configurable": {"thread_id": "mcp-demo"}, "recursion_limit": 15}
    for q in ["退款政策是什么？", "北京天气怎么样？", "用计算器算 (7+3)*5"]:
        print("你>", q)
        result = await agent.ainvoke({"messages": [HumanMessage(q)]}, cfg)
        for m in result["messages"]:
            if getattr(m, "tool_calls", None):
                for tc in m.tool_calls:
                    print(f"  [tool call] {tc['name']}({tc['args']})")
            elif m.type == "tool":
                print(f"  [tool result] {str(m.content)[:100]}")
            elif m.type == "ai" and m.content:
                print(f"  [ai] {m.content[:200]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
