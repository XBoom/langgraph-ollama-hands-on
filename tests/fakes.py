"""单元测试共用的假聊天模型（确定性）。

用假模型测图的接线（记忆、熔断、hook），不必连 Ollama 烧 token。
与普通单测里用 stub 同理：把慢/外部依赖挡在快速反馈环之外。
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakeLLM(BaseChatModel):
    """回显最后一条用户消息；从不调用工具。"""

    @property
    def _llm_type(self) -> str:
        return "fake-echo"

    def bind_tools(self, tools: Any, **kwargs: Any):
        # create_agent 会调用 bind_tools；这里 no-op：能力上「可绑工具」，
        # 但假模型从不真正发出 tool_calls。
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1].content if messages else ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=f"echo: {last}"))]
        )


class AlwaysToolLLM(BaseChatModel):
    """每轮都发出工具调用——用来验证 recursion_limit。"""

    tool_name: str = "calculator"

    @property
    def _llm_type(self) -> str:
        return "fake-always-tool"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": self.tool_name,
                    "args": {"expression": "1+1"},
                    "id": "call_loop",
                    "type": "tool_call",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])
