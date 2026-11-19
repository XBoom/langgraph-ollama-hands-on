"""对真实 Agent 跑黄金集评测（端到端）。

    .venv/bin/python -m agent.eval_run

打印表格式摘要：确定性通过率 + 可选的 LLM-judge 分数。
对应知识点：评测闭环。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from agent.eval import GOLDEN_SET, EvalResult, check_deterministic, llm_judge
from agent.graph import build_default_agent


def run_eval(use_judge: bool = False) -> list[EvalResult]:
    agent = build_default_agent(trace_path="traces/eval_trace.jsonl")
    judge_llm = ChatOllama(model="qwen2.5:14b", temperature=0) if use_judge else None
    results: list[EvalResult] = []

    for case in GOLDEN_SET:
        cfg = {"configurable": {"thread_id": f"eval-{case.id}"}, "recursion_limit": 15}
        out = agent.invoke({"messages": [HumanMessage(case.user_input)]}, cfg)
        tool_ok, answer_ok, detail = check_deterministic(case, out["messages"])

        score = None
        if use_judge and judge_llm is not None:
            final = next(
                (str(m.content) for m in reversed(out["messages"])
                 if m.type == "ai" and m.content and not getattr(m, "tool_calls", None)),
                "",
            )
            score = llm_judge(case.user_input, final, lambda p: judge_llm.invoke(p).content)

        results.append(EvalResult(case.id, tool_ok, answer_ok, score, detail))

    return results


if __name__ == "__main__":
    results = run_eval(use_judge=False)
    print(f"{'case':<16}{'tool':<6}{'answer':<8}detail")
    for r in results:
        print(f"{r.case_id:<16}{str(r.tool_ok):<6}{str(r.answer_ok):<8}{r.detail}")
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} passed")
