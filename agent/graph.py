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
from typing import Any, Sequence

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    SummarizationMiddleware,
    after_model,
    before_model,
)
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    ChatMessage,
    FunctionMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import MemorySaver

from agent.tools import get_tools

# 侧效：注册 retrieve_policy（词法向量默认）；见 agent/rag.py / docs/rag.md
import agent.rag  # noqa: F401

# demo / 默认路径共用，便于 CLI 打印本轮新增 trace 行
DEFAULT_TRACE_PATH = Path(__file__).resolve().parent.parent / "traces" / "agent.jsonl"

# 行为约束；具体工具名从 get_tools() / 调用方传入的 tools 自动生成。
DEFAULT_SYSTEM_PROMPT = (
    "你是一个简洁的助手。"
    "需要精确计算或实时数据时必须调用工具，不要凭记忆猜。"
    "回答尽量短，直接给结论。"
)


def format_tools_for_prompt(tools: Sequence[Any]) -> str:
    """从工具的 name + description 生成提示词片段（取 description 首行）。"""
    if not tools:
        return "当前未挂载任何工具。"
    lines: list[str] = ["可用工具："]
    for tool in tools:
        name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
        raw = (getattr(tool, "description", None) or "").strip()
        desc = raw.split("\n", 1)[0].strip() if raw else ""
        lines.append(f"- {name}：{desc}" if desc else f"- {name}")
    return "\n".join(lines)


def compose_system_prompt(
    base: str = DEFAULT_SYSTEM_PROMPT,
    tools: Sequence[Any] | None = None,
) -> str:
    """行为提示 + 动态工具清单。新增本地工具用 @tool 注册即可，不必改 base。"""
    tool_list = get_tools() if tools is None else tools
    return f"{base.rstrip()}\n\n{format_tools_for_prompt(tool_list)}"


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
        self._write_trace(messages, phase="before_model")
        return {"messages": self._compact(messages)}

    @staticmethod
    def _serialize_message(message: BaseMessage) -> dict[str, Any] | None:
        """把消息收成可 JSON 的形状；FunctionMessage 返回 None（不记入 traces）。"""
        if isinstance(message, FunctionMessage) or message.type == "function":
            return None

        payload: dict[str, Any] = {
            "type": message.type,
            "content": str(message.content)[:200],
        }
        if isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                payload["tool_calls"] = [
                    {"name": c.get("name"), "id": c.get("id"), "args": c.get("args")}
                    for c in tool_calls
                ]
        elif isinstance(message, ToolMessage):
            payload["name"] = message.name
            payload["tool_call_id"] = message.tool_call_id
            payload["status"] = getattr(message, "status", None)
        elif isinstance(message, SystemMessage):
            payload["name"] = message.name
        elif isinstance(message, ChatMessage):
            payload["role"] = message.role
        return payload

    def _write_trace(
        self,
        messages: list[BaseMessage],
        *,
        phase: str = "before_model",
    ) -> None:
        last = messages[-1] if messages else None
        serialized = self._serialize_message(last) if last is not None else None
        trace: dict[str, Any] = {
            "phase": phase,
            "msg_count": len(messages),
            "last_role": last.type if last else None,
            "last_content": str(last.content)[:200] if last else None,
            "message": serialized,
        }
        if last is not None and serialized is None:
            trace["skipped"] = "function"
        # 顺带带上当前线程里的 system（若有），方便对照人设是否进了 state
        systems = [
            s
            for m in messages
            if isinstance(m, SystemMessage) and (s := self._serialize_message(m))
        ]
        if systems:
            trace["system_messages"] = systems

        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace, ensure_ascii=False) + "\n")


def make_trace_middleware(trace_path: str) -> list[AgentMiddleware]:
    """模型调用前/后写 JSONL：human/ai/tool/system/chat（不含 FunctionMessage）。"""
    hook = TraceHook(trace_path)

    @before_model
    def trace_before_model(state: dict[str, Any], runtime: Any = None) -> dict[str, Any] | None:
        hook._write_trace(state.get("messages", []), phase="before_model")
        return None  # 不改写 state；压缩交给 SummarizationMiddleware

    @after_model
    def trace_after_model(state: dict[str, Any], runtime: Any = None) -> dict[str, Any] | None:
        hook._write_trace(state.get("messages", []), phase="after_model")
        return None

    return [trace_before_model, trace_after_model]


def build_agent(
    *,
    llm: Any,
    checkpointer: bool = True,
    trace_path: str | None = None,
    prompt: str = DEFAULT_SYSTEM_PROMPT,
    tools: Sequence[Any] | None = None,
    max_messages: int | None = 20,
    summarizer: Any = None,
):
    """用官方 LangChain 1.x API 组装 ReAct Agent。

    `llm` 由外部注入，方便测试用假模型；`summarizer` 可选（不传则不用摘要），
    供 SummarizationMiddleware 使用。
    `tools` 默认用 `get_tools()`（tools.py 里 @tool 自动注册的结果）。
    """
    tool_list = list(get_tools() if tools is None else tools)
    middleware: list[AgentMiddleware] = []
    if trace_path:
        middleware.extend(make_trace_middleware(trace_path))
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
        tools=tool_list,
        system_prompt=compose_system_prompt(prompt, tool_list),
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
    path = trace_path or str(DEFAULT_TRACE_PATH)
    # 生产环境可用更小/更便宜的摘要模型；这里同模型以保持全本地。
    return build_agent(llm=llm, checkpointer=True, trace_path=path, summarizer=llm)
