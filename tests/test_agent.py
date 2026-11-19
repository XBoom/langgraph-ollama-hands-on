"""最小 ReAct Agent 的测试。

TDD：这些测试先描述行为。运行：
    .venv/bin/python -m pytest -m 'not integration' -q
单元测试用假聊天模型，不需要 Ollama。
集成测试（带标记）会打真实的 qwen2.5:14b 服务。
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agent.graph import TraceHook, build_agent, compose_system_prompt, format_tools_for_prompt
from agent.tools import calculator, get_weather


# ---------------------------------------------------------------------------
# 1. 工具 / Function Calling
# ---------------------------------------------------------------------------


def test_calculator_returns_numeric_result():
    """工具是普通函数，由模型决定是否调用；结果应确定。"""
    assert calculator.invoke({"expression": "2 * (3 + 4)"}) == "14"


def test_calculator_rejects_non_expression():
    """防护：绝不 eval 任意代码——只允许算术语法。"""
    result = calculator.invoke({"expression": "__import__('os').system('echo pwned')"})
    assert "invalid" in result.lower() or "error" in result.lower()


def test_get_weather_is_deterministic_fixture():
    """离线天气工具：无网络，测试与演示可复现。"""
    out = json.loads(get_weather.invoke({"city": "北京"}))
    assert out["city"] == "北京" and "temp_c" in out


# ---------------------------------------------------------------------------
# 2. 记忆：thread_id 隔离会话
# ---------------------------------------------------------------------------


def test_memory_thread_isolation(fake_llm):
    """同一 checkpointer、不同 thread_id => 互不串话。"""
    agent = build_agent(llm=fake_llm, checkpointer=True)
    cfg_a = {"configurable": {"thread_id": "alice"}}
    cfg_b = {"configurable": {"thread_id": "bob"}}

    agent.invoke({"messages": [HumanMessage("我叫 Alice")]}, cfg_a)
    agent.invoke({"messages": [HumanMessage("我叫 Bob")]}, cfg_b)

    state_a = agent.get_state(cfg_a).values["messages"]
    state_b = agent.get_state(cfg_b).values["messages"]
    assert any("Alice" in str(m.content) for m in state_a)
    assert any("Bob" in str(m.content) for m in state_b)
    assert not any("Bob" in str(m.content) for m in state_a)


def test_memory_recall_across_turns(fake_llm):
    """同一 thread 内，后续轮次能看到更早的消息。"""
    agent = build_agent(llm=fake_llm, checkpointer=True)
    cfg = {"configurable": {"thread_id": "recall"}}
    agent.invoke({"messages": [HumanMessage("记住数字 42")]}, cfg)
    state = agent.get_state(cfg).values["messages"]
    assert any("42" in str(m.content) for m in state)


# ---------------------------------------------------------------------------
# 3. 循环熔断：recursion_limit 是断路器
# ---------------------------------------------------------------------------


def test_recursion_limit_circuit_breaker(llm_that_always_calls_tool):
    """模型若一直调工具，必须被 recursion_limit 拦住。

    用 stream() 还能断言停在哪一步（排障时希望在 trace 里看见循环，
    而不只是一个异常）。
    """
    from langgraph.errors import GraphRecursionError

    agent = build_agent(llm=llm_that_always_calls_tool, checkpointer=False)
    cfg = {"configurable": {"thread_id": "loop"}, "recursion_limit": 5}
    seen = []
    with pytest.raises(GraphRecursionError):
        for chunk in agent.stream({"messages": [HumanMessage("反复查天气")]}, cfg):
            seen.append(list(chunk.keys()))
    # 熔断应在有限个超步后触发
    assert len(seen) <= 5
    assert "tools" in seen[1]  # 循环确实发生在工具调用环路上


# ---------------------------------------------------------------------------
# 4. Trace / 上下文压缩 hook
# ---------------------------------------------------------------------------


def test_trace_hook_writes_jsonl(tmp_path):
    """每次模型调用前，向 JSONL 追加一行，便于回放 / 调试。"""
    trace_file = tmp_path / "trace.jsonl"
    hook = TraceHook(trace_path=str(trace_file))
    hook({"messages": [HumanMessage("hello")]})
    lines = trace_file.read_text().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert "msg_count" in payload and payload["msg_count"] == 1
    assert payload.get("phase") == "before_model"
    assert payload["message"]["type"] == "human"
    assert payload["message"]["content"] == "hello"


def test_trace_hook_serializes_message_types(tmp_path):
    """除 FunctionMessage 外，human/ai/tool/system/chat 都应写入可辨形状。"""
    from langchain_core.messages import (
        AIMessage,
        ChatMessage,
        FunctionMessage,
        SystemMessage,
        ToolMessage,
    )

    trace_file = tmp_path / "trace.jsonl"
    hook = TraceHook(trace_path=str(trace_file))

    hook._write_trace([SystemMessage("规矩")], phase="before_model")
    hook._write_trace([HumanMessage("你好")], phase="before_model")
    hook._write_trace(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_weather",
                        "args": {"city": "深圳"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            )
        ],
        phase="after_model",
    )
    hook._write_trace(
        [ToolMessage(content='{"ok":1}', tool_call_id="c1", name="get_weather")],
        phase="before_model",
    )
    hook._write_trace([AIMessage(content="你叫小明。")], phase="after_model")
    hook._write_trace([ChatMessage(content="旁白", role="narrator")], phase="before_model")
    # FunctionMessage 应被跳过（不写 message 字段 / 或整行标记 skipped）
    hook._write_trace(
        [FunctionMessage(name="legacy", content="x")],
        phase="before_model",
    )

    lines = [json.loads(x) for x in trace_file.read_text().splitlines()]
    assert lines[0]["message"]["type"] == "system"
    assert lines[1]["message"]["type"] == "human"
    assert lines[2]["message"]["type"] == "ai"
    assert lines[2]["message"]["tool_calls"] == [
        {"name": "get_weather", "id": "c1", "args": {"city": "深圳"}}
    ]
    assert lines[3]["message"]["type"] == "tool"
    assert lines[3]["message"]["tool_call_id"] == "c1"
    assert lines[4]["message"]["content"] == "你叫小明。"
    assert lines[5]["message"]["type"] == "chat"
    assert lines[5]["message"]["role"] == "narrator"
    assert lines[6]["message"] is None
    assert lines[6]["skipped"] == "function"


def test_compaction_trims_old_messages():
    """历史过长时：保留 system + 最近 N 条，丢掉中间。"""
    hook = TraceHook(trace_path="/dev/null", max_messages=4)
    msgs = [HumanMessage(f"m{i}") for i in range(10)]
    trimmed = hook._compact(msgs)
    assert len(trimmed) <= 4
    assert trimmed[-1].content == "m9"


def test_system_prompt_lists_tools_dynamically():
    """提示词工具清单随 tools 变化，不必手写工具名。"""
    block = format_tools_for_prompt([calculator, get_weather])
    assert "calculator" in block and "get_weather" in block
    assert "可用工具" in block

    @tool
    def ping() -> str:
        """探活。"""
        return "pong"

    composed = compose_system_prompt("你是助手。", [ping])
    assert "ping" in composed and "探活" in composed
    assert "calculator" not in composed


def test_local_tools_auto_registered():
    """tools.py 里用 @tool 定义的工具应进入 get_tools，无需维护全局列表。"""
    from agent.tools import get_tools

    names = {t.name for t in get_tools()}
    assert {"calculator", "get_weather"} <= names


# ---------------------------------------------------------------------------
# 集成（真实 Ollama）——显式用 -m integration 运行
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_real_ollama_end_to_end():
    from agent.graph import build_default_agent

    agent = build_default_agent()
    cfg = {"configurable": {"thread_id": "integration"}}
    result = agent.invoke(
        {"messages": [HumanMessage("用计算器算 12*12，然后只回复数字")]},
        cfg,
    )
    assert result["messages"][-1].content.strip() == "144"
