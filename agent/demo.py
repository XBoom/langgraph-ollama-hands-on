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
import json
from pathlib import Path

from langchain_core.messages import HumanMessage

from agent.graph import DEFAULT_TRACE_PATH, build_default_agent


def _print_new_trace_lines(trace_path: Path, offset: int) -> int:
    """把本轮新追加的 JSONL 打到终端，方便对照 human/ai/tool/system 形状。"""
    if not trace_path.exists():
        return offset
    data = trace_path.read_bytes()
    chunk = data[offset:].decode("utf-8", errors="replace")
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [trace] {line[:200]}")
            continue
        msg = row.get("message")
        phase = row.get("phase")
        if msg is None:
            print(f"  [trace:{phase}] skipped={row.get('skipped')}")
            continue
        extra = ""
        if msg.get("tool_calls"):
            extra = f" tool_calls={msg['tool_calls']}"
        elif msg.get("tool_call_id"):
            extra = f" tool_call_id={msg['tool_call_id']} name={msg.get('name')}"
        elif msg.get("role"):
            extra = f" role={msg['role']}"
        print(
            f"  [trace:{phase}] type={msg.get('type')} "
            f"content={str(msg.get('content'))[:120]!r}{extra}"
        )
    return len(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thread", default="demo", help="会话 / thread id")
    args = parser.parse_args()

    agent = build_default_agent()
    cfg = {
        "configurable": {"thread_id": args.thread},
        "recursion_limit": 15,  # 熔断：防止工具调用死循环
    }
    print(f"Agent ready (thread={args.thread}). 输入 q 退出。")
    print(f"Trace → {DEFAULT_TRACE_PATH}（终端同步打印本轮新增行）\n")

    while True:
        user = input("你> ").strip()
        if user.lower() in {"q", "quit", "exit"}:
            break
        if not user:
            continue

        trace_offset = (
            DEFAULT_TRACE_PATH.stat().st_size if DEFAULT_TRACE_PATH.exists() else 0
        )

        # 流式输出，便于观察 Thought / Action / Observation 循环（可观测性）
        # stream_mode="updates" 时：middleware 节点常返回 payload=None（仅表示跑过）；
        # create_agent 图里模型节点名是 "model"（不是旧版的 "agent"）。
        for step in agent.stream(
            {"messages": [HumanMessage(content=user)]}, cfg, stream_mode="updates"
        ):
            for node, payload in step.items():
                if not isinstance(payload, dict):
                    continue
                msgs = payload.get("messages") or []
                if not msgs:
                    continue
                last = msgs[-1]
                if node == "tools":
                    print(f"  [tool] {last.name}: {str(last.content)[:120]}")
                elif node in {"model", "agent"} and getattr(last, "type", None) == "ai":
                    if last.content:
                        print(f"  [ai] {str(last.content)[:200]}")
                    elif getattr(last, "tool_calls", None):
                        names = [c.get("name") for c in last.tool_calls]
                        print(f"  [ai] tool_calls={names}")

        _print_new_trace_lines(DEFAULT_TRACE_PATH, trace_offset)
        print()


if __name__ == "__main__":
    main()
