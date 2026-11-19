# Middleware、记忆与评测

> 本仓库对照说明。Tool / MCP / RAG 见同目录其它文档。  
> 代码锚点：[`agent/graph.py`](../agent/graph.py) · [`agent/demo.py`](../agent/demo.py) · [`agent/eval.py`](../agent/eval.py) · [`agent/eval_run.py`](../agent/eval_run.py)

---

## 1. Middleware 是什么？

在 `create_agent` 里，**middleware = 挂在「调模型前后」的插件**，不改变 ReAct 环本身（model ↔ tools），只改上下文或加观测。

本仓两类：

| 中间件 | 时机 | 作用 |
|---|---|---|
| `make_trace_middleware` | `@before_model` / `@after_model` | 把最新消息序列化进 `traces/*.jsonl` |
| `SummarizationMiddleware` | 消息过多时 | 用摘要模型压缩历史，控制上下文长度 |

`build_agent(..., trace_path=..., summarizer=...)` 按需组装。`TraceHook` 是单测兼容层（`_compact` / 写盘），生产路径走 middleware 装饰器。

**和 ReAct 的关系**：环仍是 Thought → Action → Observation；middleware 是环上的挂钩，不是另一种 agent 范式。

---

## 2. 短期记忆：checkpointer + thread_id

| 概念 | 本仓 |
|---|---|
| checkpointer | `MemorySaver()`：进程内会话快照 |
| `thread_id` | `config["configurable"]["thread_id"]`：哪一本聊天本 |
| 每轮输入 | 通常只交本轮 `HumanMessage`；旧消息由 checkpointer 合并 |

无 checkpointer → 每轮失忆。有 checkpointer 但乱换 `thread_id` → 等于新开一本。细节见 [消息协议.md](./消息协议.md)。

`demo --thread`、`eval_run` 的 `eval-{case.id}` 都是在选线程。

---

## 3. 熔断：`recursion_limit`

工具来回可能死循环。本仓在 **config 顶层**设 `recursion_limit`（如 15），超限抛 `GraphRecursionError`。  
这与 middleware 无关，是图执行预算。

---

## 4. 评测闭环

[`eval.py`](../agent/eval.py) 两层：

1. **确定性**：是否调对工具、参数（空白归一化）、答案是否含关键字。  
2. **LLM-judge（可选）**：开放性打分；与确定性分开，避免主观噪声掩盖功能回归。

黄金集含：`calc_basic`、`weather_lookup`、`policy_rag_refund`（`retrieve_policy`）。  
跑：`poetry run python -m agent.eval_run`。

---

## 5. 阅读顺序建议

1. [消息协议.md](./消息协议.md) — 消息与 thread  
2. [tools.md](./tools.md) — tool_calls 环  
3. 本文 — 记忆 / 压缩 / 观测 / 评测  
4. [mcp.md](./mcp.md) · [rag.md](./rag.md) — 外部能力与检索  

---

## 6. 证据

- [src: langchain create_agent middleware] before/after_model  
- [src: LangGraph MemorySaver / thread_id]  
- [src: 本仓] `graph.py` · `demo.py` · `eval.py` · `test_agent.py`
