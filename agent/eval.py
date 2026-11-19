"""评测框架：黄金集 + LLM-as-judge。

最小版「评测 / SLO」实现：
- 黄金集：固定用例，带期望工具调用 / 期望答案子串。
- 确定性检查：是否调对工具、参数是否正确（不需要 LLM）。
- LLM-judge：对开放性回答，用第二个模型打 faithfulness / helpfulness 分。

为何分两层：确定性检查便宜且客观；LLM-judge 覆盖主观质量，但有已知偏差
（自我偏好、啰嗦偏好）。分开后，judge 失败不会掩盖功能回归。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


@dataclass
class EvalCase:
    id: str
    user_input: str
    expected_tool: str | None = None
    expected_args: dict[str, Any] = field(default_factory=dict)
    expected_answer_contains: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    case_id: str
    tool_ok: bool
    answer_ok: bool
    judge_score: float | None = None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.tool_ok and self.answer_ok


def _tool_calls_in(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            calls.extend(m.tool_calls)
    return calls


def check_deterministic(case: EvalCase, messages: list[BaseMessage]) -> tuple[bool, bool, str]:
    """返回 (tool_ok, answer_ok, detail)。纯函数，可完整单测。"""
    calls = _tool_calls_in(messages)
    detail_parts: list[str] = []

    tool_ok = True
    if case.expected_tool is not None:
        matched = [c for c in calls if c.get("name") == case.expected_tool]
        tool_ok = bool(matched)
        if not tool_ok:
            detail_parts.append(f"expected tool '{case.expected_tool}', got {[c.get('name') for c in calls]}")
        elif case.expected_args and matched:
            actual = matched[0].get("args", {})
            for k, v in case.expected_args.items():
                # 归一化空白：模型常传 "12 * 12"，期望是 "12*12"。
                # 工具参数比语义相等，不比字节级相等。
                def _norm(x: Any) -> str:
                    return str(x).replace(" ", "").replace("　", "")

                if _norm(actual.get(k)) != _norm(v):
                    tool_ok = False
                    detail_parts.append(f"arg {k}: expected {v}, got {actual.get(k)}")

    answer_ok = True
    final = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            final = str(m.content)
            break
    for needle in case.expected_answer_contains:
        if needle not in final:
            answer_ok = False
            detail_parts.append(f"answer missing '{needle}': {final[:80]!r}")

    return tool_ok, answer_ok, "; ".join(detail_parts)


def llm_judge(question: str, answer: str, judge: Callable[[str], str]) -> float:
    """用评判模型给开放性回答打 0–1 分。

    `judge` 由外部注入（字符串 prompt → 字符串分数），单测可 stub，
    集成测试用真实 Ollama。要求只输出一个数字，并做防御性解析——
    评判模型经常把分数包在散文里。
    """
    import re

    prompt = (
        "你是严格评测员。问题：{q}\n回答：{a}\n"
        "请只输出 0 到 1 之间的一个小数分数（1 分=完全正确且简洁），不要其他文字。"
    ).format(q=question, a=answer)
    raw = judge(prompt)
    match = re.search(r"(0(?:\.\d+)?|1(?:\.0+)?)", raw)
    if not match:
        raise ValueError(f"judge returned no score: {raw[:100]!r}")
    return max(0.0, min(1.0, float(match.group(1))))


GOLDEN_SET: list[EvalCase] = [
    EvalCase(
        id="calc_basic",
        user_input="用计算器算 12*12",
        expected_tool="calculator",
        expected_args={"expression": "12*12"},
        expected_answer_contains=["144"],
    ),
    EvalCase(
        id="weather_lookup",
        user_input="北京今天天气怎么样？",
        expected_tool="get_weather",
        expected_args={"city": "北京"},
        expected_answer_contains=["北京"],
    ),
]
