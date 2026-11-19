# docs · 与代码对照的说明

本目录文档**依赖本仓库阅读**，不按独立文章发布。文档只写概念 + 指向 `agent/` / `tests/` 的锚点；可运行入口以代码为准。

| 文档 | 说明 | 主要代码锚点 |
|---|---|---|
| [消息协议.md](./消息协议.md) | HumanMessage / 状态 / checkpointer / thread_id | `agent/demo.py` · `agent/graph.py` · `tests/fakes.py` |
| [tools.md](./tools.md) | Tool 是什么；LangGraph/`create_agent` 里 model↔tools 环与 Schema/`tool_calls` | `agent/graph.py` · `agent/demo.py` · `agent/tools.py` |
| [mcp.md](./mcp.md) | MCP 是什么；与 Function Calling 正交；`tools/list`·`tools/call`·stdio 接入图 | `agent/mcp_server.py` · `mcp_client.py` · `mcp_demo.py` |
| [rag.md](./rag.md) | RAG / Agentic 检索当 Tool；词法与 Ollama embedding | `agent/rag.py` · `rag_data/` · `rag_demo.py` · `tests/test_rag.py` |

约定：改协议行为先改代码，再改文档里的链接与一两句说明。
