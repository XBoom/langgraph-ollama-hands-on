"""消息协议示例：假模型 + 工具 + MemorySaver（无需 Ollama）。

配合说明文档：docs/消息协议.md

运行（在仓库根目录）：
    poetry run python docs/examples/messages_protocol_demo.py
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver


@tool
def calculator(expression: str) -> str:
    """计算简单加法。本 demo 为演示协议，仅识别 1+1。"""
    if expression.replace(" ", "") == "1+1":
        return "2"
    return f"unsupported: {expression}"


class DemoLLM(BaseChatModel):
    """假模型：按消息列表决定「调工具 / 最终答 / 回忆上一轮结果」。"""

    @property
    def _llm_type(self) -> str:
        return "demo-scripted"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        text = str(last_human.content) if last_human else ""

        if last_human is not None:
            after = messages[messages.index(last_human) + 1 :]
            for m in after:
                if isinstance(m, ToolMessage):
                    msg = AIMessage(content=f"计算结果是 {m.content}。")
                    return ChatResult(generations=[ChatGeneration(message=msg)])

        if any(k in text for k in ("结果", "多少", "刚才")):
            for m in reversed(messages):
                if isinstance(m, ToolMessage):
                    msg = AIMessage(content=f"刚才算出来是 {m.content}。")
                    return ChatResult(generations=[ChatGeneration(message=msg)])

        if any(ch in text for ch in "+-*/"):
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculator",
                        "args": {"expression": "1+1"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        msg = AIMessage(content=f"收到：{text}")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def dump_messages(messages: list[BaseMessage]) -> None:
    for i, m in enumerate(messages, 1):
        extra = ""
        if getattr(m, "tool_calls", None):
            extra = f" tool_calls={m.tool_calls}"
        elif getattr(m, "tool_call_id", None):
            extra = f" tool_call_id={m.tool_call_id}"
        print(f"  {i}. [{m.type}] {str(m.content)[:60]!r}{extra}")


def main() -> None:
    agent = create_agent(
        model=DemoLLM(),
        tools=[calculator],
        system_prompt="你是助手；需要计算时调用 calculator。",
        checkpointer=MemorySaver(),
    )
    cfg = {
        "configurable": {"thread_id": "demo-thread"},
        "recursion_limit": 10,
    }

    print("=== 第 1 轮：Human → AI(tool_calls) → Tool → AI ===")
    r1 = agent.invoke({"messages": [HumanMessage("帮我算 1+1")]}, cfg)
    dump_messages(r1["messages"])

    print("\n=== 第 2 轮：只交新句；同一 thread_id，历史由 checkpointer 拼回 ===")
    r2 = agent.invoke(
        {"messages": [HumanMessage("我刚才算的结果是多少？")]},
        cfg,
    )
    dump_messages(r2["messages"])
    print("\n最后一条 AI:", r2["messages"][-1].content)


if __name__ == "__main__":
    main()
