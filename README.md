# LangGraph + Ollama Agent 实战

用本地 Ollama（`qwen2.5:14b`）跑通一套最小但具备生产形状的 Agent：ReAct、Function Calling、短期记忆、熔断、上下文压缩、可观测性、MCP（多 Server）、Agentic RAG（可选持久化）、评估闭环。

> 版本：langgraph **1.2.22** / langchain **1.5.0** / langchain-core 1.8.1 / langchain-ollama 1.1.0 /
> langchain-mcp-adapters / numpy / Python 3.12.x（签名核对 2026-11-17；RAG/P2 于 2026-11-19）

**分支约定**：WorkSpace `AGENTS.md` Git Flow + skill `git-flow`。  
**对照文档**：[docs/](./docs/)（消息协议 / tools / MCP / RAG / middleware·记忆·评测 / [待办](./docs/待办.md)）。

---

## 1. 覆盖的知识点

| 知识点 | 本项目中的实现 |
|---|---|
| ReAct / Function Calling | `create_agent` + tools；`tool_calls` → ToolNode |
| 短期记忆 | `MemorySaver` + `thread_id` |
| 死循环熔断 | `config.recursion_limit` |
| 上下文压缩 | `SummarizationMiddleware` |
| 可观测性 | `@before_model` / `@after_model` → JSONL；demo 同步打印 |
| MCP | `docs` + `weather` 两个 stdio Server；`discover_mcp_tools(...)` |
| Agentic RAG | `retrieve_policy`；词法默认；可选 Ollama embedding；可选 `RAG_PERSIST_PATH` |
| 评估闭环 | 黄金集（含 RAG）+ 确定性 + 可选 LLM-judge |

---

## 2. 目录

```
agent/
  graph.py / tools.py / weather_fixture.py / policy_snippets.py
  demo.py
  mcp_server.py / mcp_weather_server.py / mcp_client.py / mcp_demo.py
  rag.py / rag_data/ / rag_demo.py
  eval.py / eval_run.py
docs/          # 对照说明 + 待办
tests/
traces/        # gitignore
rag_store/     # gitignore（可选向量 JSON）
```

---

## 3. 要点

- **工具注册**：`@tool` → `get_tools()`；Schema 经 `bind_tools` 进请求 `tools` 字段。  
- **MCP**：政策 Server + 天气 Server；`mcp_demo` 用 MCP 天气并去掉本地同名工具。本地 `get_weather` 仍供 demo/单测（同源 `weather_fixture`）。  
- **RAG**：默认内存建库；`RAG_PERSIST_PATH=./rag_store` 时 `InMemoryVectorStore.dump/load`。  
- **评测**：`calc_basic` / `weather_lookup` / `policy_rag_refund`。

详解：[docs/middleware与记忆评测.md](./docs/middleware与记忆评测.md) · [docs/mcp.md](./docs/mcp.md) · [docs/rag.md](./docs/rag.md)。

---

## 4. 测试与快速开始

```bash
poetry install
poetry run python -m pytest -m 'not integration' -q   # 29 用例 + 2 integration（以 collect 为准）
poetry run python -m agent.demo --thread demo
poetry run python -m agent.mcp_demo                   # docs + weather MCP
poetry run python -m agent.rag_demo
# RAG_PERSIST_PATH=./rag_store poetry run python -m agent.rag_demo
# RAG_EMBEDDINGS=ollama poetry run python -m agent.rag_demo
poetry run python -m agent.eval_run
```

---

## 证据

- LangChain `create_agent` / middleware / MCP adapter / `InMemoryVectorStore.dump|load`  
- [LangGraph Agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag)  
- [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
