"""Agentic RAG 演示：retrieve_policy 工具 + 本地 Ollama 聊天。

默认用词法向量（无需 embedding 模型）。真语义：

    RAG_EMBEDDINGS=ollama poetry run python -m agent.rag_demo
    # 需先：ollama pull nomic-embed-text
"""

from __future__ import annotations

import os

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from agent.graph import DEFAULT_SYSTEM_PROMPT, build_agent
from agent.rag import ensure_rag_registered
from agent.tools import get_tools

TRACE = "traces/rag_agent.jsonl"


def main() -> None:
    mode = os.environ.get("RAG_EMBEDDINGS", "lexical").strip().lower()
    if mode not in {"lexical", "ollama"}:
        raise SystemExit(f"RAG_EMBEDDINGS must be lexical|ollama, got {mode!r}")

    ensure_rag_registered(embeddings=mode, force=True)  # type: ignore[arg-type]
    names = [t.name for t in get_tools()]
    print(f"embeddings={mode} tools={names}")

    llm = ChatOllama(
        model="qwen2.5:14b",
        temperature=0,
        base_url="http://127.0.0.1:11434",
    )
    base = (
        DEFAULT_SYSTEM_PROMPT
        + " 政策/质保/配送问题必须先调用 retrieve_policy，再根据检索片段回答并点出 chunk_id。"
    )
    agent = build_agent(
        llm=llm,
        checkpointer=True,
        trace_path=TRACE,
        prompt=base,
        tools=get_tools(),
    )
    cfg = {"configurable": {"thread_id": "rag-demo"}, "recursion_limit": 15}

    for q in ["退款要几天到账？", "电子产品质保多久？", "1+1等于几"]:
        print("你>", q)
        result = agent.invoke({"messages": [HumanMessage(q)]}, cfg)
        for m in result["messages"][-6:]:
            if getattr(m, "tool_calls", None):
                for tc in m.tool_calls:
                    print(f"  [tool call] {tc['name']}({tc['args']})")
            elif m.type == "tool":
                print(f"  [tool result] {str(m.content)[:180]}…")
            elif m.type == "ai" and m.content:
                print(f"  [ai] {m.content[:240]}")
        print()


if __name__ == "__main__":
    main()
