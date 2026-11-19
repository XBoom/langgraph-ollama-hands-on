"""图（Agent）组装（LangChain 1.x / LangGraph 1.2+）。

三层结构，对应三类知识点：
1. create_agent            —— Thought / Action / Observation 循环（ReAct）
2. MemorySaver + thread_id —— 短期 / 会话记忆
3. middleware              —— 上下文压缩 + 链路追踪（生产必备）

源码核对说明：2026-11-17 对照已安装 langchain 1.5.0 / langgraph 1.2.22
（inspect.signature）。旧版 prebuilt.create_react_agent 在 LangGraph 1.0 弃用、
2.0 移除；新入口为 `from langchain.agents import create_agent`，
`prompt` → `system_prompt`，`pre/post_model_hook` → `middleware`。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    SummarizationMiddleware,
    before_model,
)
from langchain_core.messages import AnyMessage, BaseMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.tools import calculator, get_weather

TOOLS = [calculator, get_weather]

DEFAULT_SYSTEM_PROMPT = (
    "你是一个简洁的助手。可用工具：calculator（算术）、get_weather（天气）。"
    "需要精确计算或实时数据时必须调用工具，不要凭记忆猜。"
    "回答尽量短，直接给结论。"
)


class TraceHook:
    """兼容层，供单测使用：写日志 + 裁剪消息。

    新 API 下等价逻辑在下方 `make_trace_middleware`。
    保留本类是因为测试会断言纯函数 _compact() 与 JSONL 写入。
    """

    def __init__(self, trace_path: str, max_messages: int | None = 20) -> None:
        self.trace_path = Path(trace_path)
        self.max_messages = max_messages

    def _compact(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if self.max_messages is None or len(messages) <= self.max_messages:
            return list(messages)
        system = [m for m in messages if isinstance(m, SystemMessage)]
        recent = [m for m in messages if not isinstance(m, SystemMessage)]
        kept = recent[-(self.max_messages - len(system)) :]
        return system + kept

    def __call__(self, state: dict[str, Any]) -> dict[str, list[AnyMessage]]:
        messages: list[BaseMessage] = state.get("messages", [])
        self._write_trace(messages)
        return {"messages": self._compact(messages)}

    def _write_trace(self, messages: list[BaseMessage]) -> None:
        trace = {
            "msg_count": len(messages),
            "last_role": messages[-1].type if messages else None,
            "last_content": str(messages[-1].content)[:200] if messages else None,
        }
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace, ensure_ascii=False) + "\n")


def make_trace_middleware(trace_path: str) -> AgentMiddleware:
    """新 API 中间件：每次调用模型前追加一行 JSONL。

    这是官方扩展点，替代旧的 pre_model_hook。用装饰器写法，声明式且可与其他
    middleware 组合。
    """
    hook = TraceHook(trace_path)

    @before_model
    def trace_before_model(state: dict[str, Any], runtime: Any = None) -> dict[str, Any] | None:
        hook._write_trace(state.get("messages", []))
        return None  # 不改写 state；压缩交给 SummarizationMiddleware

    return trace_before_model


def build_agent(
    *,
    llm: Any,
    checkpointer: bool = True,
    trace_path: str | None = None,
    prompt: str = DEFAULT_SYSTEM_PROMPT,
    max_messages: int | None = 20,
    summarizer: Any = None,
):
    """用官方 LangChain 1.x API 组装 ReAct Agent。

    `llm` 由外部注入，方便测试用假模型；`summarizer` 可选（不传则不用摘要），
    供 SummarizationMiddleware 使用。
    """
    middleware: list[AgentMiddleware] = []
    if trace_path:
        middleware.append(make_trace_middleware(trace_path))
    if summarizer is not None:
        middleware.append(
            SummarizationMiddleware(
                model=summarizer,
                trigger=("messages", max_messages or 20),
                keep=("messages", max(4, (max_messages or 20) // 2)),
            )
        )

    return create_agent(
        model=llm,
        tools=TOOLS,
        system_prompt=prompt,
        checkpointer=MemorySaver() if checkpointer else None,
        middleware=middleware,
    )


def build_default_agent(trace_path: str | None = None):
    """偏生产默认配置：本地 Ollama qwen2.5:14b。"""
    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model="qwen2.5:14b",
        temperature=0,
        num_ctx=8192,
        base_url="http://127.0.0.1:11434",
    )
    path = trace_path or str(
        Path(__file__).resolve().parent.parent / "traces" / "agent.jsonl"
    )
    # 生产环境可用更小/更便宜的摘要模型；这里同模型以保持全本地。
    return build_agent(llm=llm, checkpointer=True, trace_path=path, summarizer=llm)
