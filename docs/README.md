# docs · 与代码对照的说明

本目录文档**依赖本仓库阅读**，不按独立文章发布。大段可运行示例放在 `docs/examples/` 或直接看 `agent/`，文档只写概念 + 指向代码的锚点。

| 文档 | 说明 | 主要代码锚点 |
|---|---|---|
| [消息协议.md](./消息协议.md) | HumanMessage / 状态 / checkpointer / thread_id | `agent/demo.py` · `agent/graph.py` · `docs/examples/messages_protocol_demo.py` · `tests/fakes.py` |

约定：改协议行为先改代码与示例脚本，再改文档里的链接与一两句说明，避免把 Demo 全文贴进 Markdown。
