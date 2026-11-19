"""支持 MCP 的 Agent 演示：进程内 @tool + 远程 MCP 工具同图运行。

运行：
    .venv/bin/python -m agent.mcp_demo

说明 MCP 与 Function Calling 的关系：
Function Calling 是模型请求调用工具的机制；
MCP 是让 Agent 发现/调用「跑在另一进程里的工具」的协议。
二者可组合——本 Agent 同时具备两种工具。
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
    remote_tools = await discover_mcp_tools()
    all_tools = [*get_tools(), *remote_tools]
    print(f"Discovered {len(remote_tools)} MCP tool(s): {[t.name for t in remote_tools]}")

    llm = ChatOllama(model="qwen2.5:14b", temperature=0, base_url="http://127.0.0.1:11434")
    # 工具清单从 all_tools 自动生成；政策类工具随 MCP 发现出现，无需写死名字
    base = (
        DEFAULT_SYSTEM_PROMPT
        + " 需要查退款/配送等政策时，优先使用知识库类工具（主题如 refund / shipping）。"
    )
    agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=compose_system_prompt(base, all_tools),
        middleware=make_trace_middleware(TRACE),
    )
    cfg = {"configurable": {"thread_id": "mcp-demo"}, "recursion_limit": 15}
    for q in ["退款政策是什么？", "用计算器算 (7+3)*5"]:
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
