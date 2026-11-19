# docs · 与代码对照的说明

本目录文档**依赖本仓库阅读**，不按独立文章发布。文档只写概念 + 指向 `agent/` / `tests/` 的锚点；可运行入口以代码为准。

| 文档 | 说明 | 主要代码锚点 |
|---|---|---|
| [消息协议.md](./消息协议.md) | HumanMessage / 状态 / checkpointer / thread_id | `agent/demo.py` · `agent/graph.py` · `agent/tools.py` · `tests/fakes.py` |

约定：改协议行为先改代码，再改文档里的链接与一两句说明。
