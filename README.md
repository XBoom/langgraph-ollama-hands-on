# LangGraph + Ollama Agent 实战

用本地 Ollama（`qwen2.5:14b`）跑通一套最小但具备生产形状的 Agent：ReAct 循环、Function Calling、短期记忆、死循环熔断、上下文压缩、可观测性、MCP、Agentic RAG、评估闭环。

> 版本（源码读签名确认，2026-11-17；RAG/numpy 于 2026-11-19 补齐）：langgraph **1.2.22** / langchain **1.5.0** /
> langchain-core 1.8.1 / langchain-ollama 1.1.0 / langchain-mcp-adapters / numpy / Python 3.12.x

**分支约定**：WorkSpace `AGENTS.md`「Git Flow 闸门」+ skill `git-flow`。  
**对照文档**：[docs/](./docs/)（消息协议 / tools / MCP / RAG / [待办](./docs/待办.md)）；索引 [docs/README.md](./docs/README.md)。

---

## 1. 覆盖的知识点

| 知识点 | 本项目中的实现 |
|---|---|
| ReAct / Function Calling | `create_agent` + tools；模型发 `tool_calls`，图侧 ToolNode 执行 |
| 短期记忆 | `MemorySaver` + `thread_id` |
| 死循环熔断 | `config.recursion_limit` → `GraphRecursionError` |
| 上下文压缩 | `SummarizationMiddleware`；`TraceHook._compact` 裁剪 |
| 可观测性 | `@before_model` + `@after_model` 写 JSONL；`demo` 可同步打印本轮新增行 |
| MCP | stdio FastMCP + 运行时 `tools/list`；可与本地 `@tool` 混用 |
| Agentic RAG | `retrieve_policy`：`rag_data` 切块 + 向量检索当 Tool（默认词法；可选 Ollama embedding） |
| 评估闭环 | 黄金集（含 RAG）+ 确定性检查 + 可选 LLM-judge |

---

## 2. 目录与职责

```
langgraph-ollama-hands-on/
├── agent/
│   ├── graph.py            # Agent 工厂
│   ├── tools.py            # 进程内工具 + 注册表
│   ├── policy_snippets.py  # 政策短摘要真源（MCP 与 RAG 对齐）
│   ├── demo.py             # 交互 CLI + stream + trace 打印
│   ├── mcp_server.py / mcp_client.py / mcp_demo.py
│   ├── rag.py / rag_data/ / rag_demo.py
│   ├── eval.py / eval_run.py
├── tests/
├── traces/                 # gitignore
├── docs/
└── README.md
```

---

## 3. 核心模块要点

### 工具与注册

- `calculator` / `get_weather`：`@tool` 自动进 `get_tools()`。  
- Schema：docstring + 类型 → `bind_tools` 请求字段 `tools`（见 [docs/tools.md](./docs/tools.md)）。

### Graph

- `create_agent` + `MemorySaver` + middleware（trace / 摘要）。  
- `import agent.rag` 侧效注册 `retrieve_policy`。

### MCP vs RAG 知识

| | MCP `lookup_docs` | RAG `retrieve_policy` |
|---|---|---|
| 查找 | topic 键 | 向量相似 |
| 文案 | `policy_snippets.POLICY_BY_TOPIC` | `rag_data/*.md`（须与摘要事实一致） |
| 目的 | 协议 / 跨进程 | Agentic 检索 |

### 评测

黄金集：`calc_basic`、`weather_lookup`、`policy_rag_refund`（期望工具 `retrieve_policy`）。

---

## 4. 模块 ↔ 知识点

| 文件 / 机制 | 知识点 |
|---|---|
| `tools.py` | Tool schema、执行边界 |
| `graph.py` | ReAct、`create_agent`、middleware |
| `rag.py` + `rag_data/` | Agentic RAG |
| `policy_snippets.py` | MCP/RAG 政策摘要对齐 |
| `mcp_*` | MCP list/call、stdio |
| `eval*` | 黄金集 / judge |
| `MemorySaver` + `thread_id` | 会话记忆 |
| `recursion_limit` | 熔断 |

---

## 5. 测试

日常：

```bash
poetry run python -m pytest -m 'not integration' -q
```

**26** 个非集成用例 + **2** 个 `@pytest.mark.integration`（真 Ollama 对话；Ollama embedding 冒烟，缺模型则 skip）。以 `pytest --collect-only` 为准。

---

## 6. 快速开始

```bash
poetry install
poetry run python -m pytest -m 'not integration' -q
poetry run python -m agent.demo --thread demo
poetry run python -m agent.mcp_demo
poetry run python -m agent.rag_demo
# RAG_EMBEDDINGS=ollama poetry run python -m agent.rag_demo   # 需 nomic-embed-text
poetry run python -m agent.eval_run
```

缺口与可选增强见 [docs/待办.md](./docs/待办.md)。

---

## 7. 总结

可跑的 LangGraph Agent 学习骨架：记忆、工具、熔断、trace、MCP、RAG、评测齐全；文档与代码对照，不独立灌水。

---

## 证据 / 来源

- LangChain `create_agent` / middleware / MCP adapter：已装包 `inspect.signature`（2026-11-17）  
- [LangGraph Agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag)  
- [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)  
- [ChatOllama](https://docs.langchain.com/oss/python/integrations/chat/ollama)
