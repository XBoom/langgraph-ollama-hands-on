"""交互式 CLI 演示。

运行：
    .venv/bin/python -m agent.demo            # 新会话
    .venv/bin/python -m agent.demo --thread my-id   # 恢复某会话

可试：
    帮我算 (12 + 8) * 3
    北京天气怎么样？
    我叫小明，记住我   ->   我叫什么？   （跨轮记忆）
"""

from __future__ import annotations

import argparse

from langchain_core.messages import HumanMessage

from agent.graph import build_default_agent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", default="demo", help="会话 / thread id")
    args = parser.parse_args()

    agent = build_default_agent()
    cfg = {
        "configurable": {"thread_id": args.thread},
        "recursion_limit": 15,  # 熔断：防止工具调用死循环
    }
    print(f"Agent ready (thread={args.thread}). 输入 q 退出。\n")

    while True:
        user = input("你> ").strip()
        if user.lower() in {"q", "quit", "exit"}:
            break
        if not user:
            continue

        # 流式输出，便于观察 Thought / Action / Observation 循环（可观测性）
        for step in agent.stream(
            {"messages": [HumanMessage(content=user)]}, cfg, stream_mode="updates"
        ):
            for node, payload in step.items():
                msgs = payload.get("messages", [])
                if not msgs:
                    continue
                last = msgs[-1]
                if node == "tools":
                    print(f"  [tool] {last.name}: {str(last.content)[:120]}")
                elif node == "agent" and last.type == "ai" and last.content:
                    print(f"  [ai] {last.content[:200]}")
        print()


if __name__ == "__main__":
    main()
