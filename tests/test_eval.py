"""评测框架测试。TDD：先锁行为再实现。"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.eval import (
    EvalCase,
    check_deterministic,
    llm_judge,
    GOLDEN_SET,
)


def _msgs_with_tool():
    return [
        HumanMessage("用计算器算 12*12"),
        AIMessage("", tool_calls=[{"name": "calculator", "args": {"expression": "12*12"}, "id": "c1"}]),
        ToolMessage("144", tool_call_id="c1"),
        AIMessage("答案是 144"),
    ]


def test_check_deterministic_all_pass():
    case = GOLDEN_SET[0]
    tool_ok, answer_ok, detail = check_deterministic(case, _msgs_with_tool())
    assert tool_ok and answer_ok, detail


def test_check_deterministic_wrong_tool():
    case = EvalCase(id="x", user_input="?", expected_tool="get_weather")
    msgs = [
        AIMessage("", tool_calls=[{"name": "calculator", "args": {}, "id": "c1"}]),
        AIMessage("done"),
    ]
    tool_ok, answer_ok, detail = check_deterministic(case, msgs)
    assert not tool_ok
    assert "expected tool" in detail


def test_check_deterministic_wrong_arg():
    case = EvalCase(
        id="x", user_input="?", expected_tool="calculator",
        expected_args={"expression": "12*12"},
    )
    msgs = [
        AIMessage("", tool_calls=[{"name": "calculator", "args": {"expression": "1+1"}, "id": "c1"}]),
        AIMessage("2"),
    ]
    tool_ok, _, detail = check_deterministic(case, msgs)
    assert not tool_ok and "arg expression" in detail


def test_judge_score_parsing():
    """评判模型常把分数包在散文里——做防御性解析。"""
    assert llm_judge("q", "a", lambda _: "0.85") == 0.85
    assert llm_judge("q", "a", lambda _: "评分：0.5 分") == 0.5
    assert llm_judge("q", "a", lambda _: "1.0") == 1.0


def test_judge_score_clamped():
    assert llm_judge("q", "a", lambda _: "1.5") == 1.0
