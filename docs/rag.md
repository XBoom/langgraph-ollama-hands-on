# 什么是 RAG？它和 Tool / Agent / MCP 什么关系？

> 本文是**本仓库的对照说明**。实现落点：[`agent/rag.py`](../agent/rag.py) · [`agent/rag_data/`](../agent/rag_data/) · [`agent/rag_demo.py`](../agent/rag_demo.py)。  
> 相关：[tools.md](./tools.md) · [mcp.md](./mcp.md) · [消息协议.md](./消息协议.md)。

---

## 1. 一句话定义

**RAG = Retrieval-Augmented Generation（检索增强生成）**：回答前先从外部知识库**取出相关片段**，把片段塞进模型上下文，再生成答案。

| 步 | 名字 | 干什么 | 本仓 |
|---|---|---|---|
| R | Retrieve | 按问题找文档块 | `retrieve_policy` → 向量相似检索 |
| A | Augment | 片段写入对话 | `ToolMessage` 内容 |
| G | Generate | 基于问题+片段作答 | model 节点再调 LLM |

---

## 2. 本仓接线（Agentic RAG）

采用 **检索当 Tool**（不是固定「先检索再生成」流水线）：

```text
语料 agent/rag_data/*.md
  → 空行切块 + metadata(chunk_id, source)
  → Embedding（默认词法 / 可选 Ollama nomic-embed-text）
  → InMemoryVectorStore
  → create_retriever_tool → register_tool("retrieve_policy")
  → create_agent(tools=get_tools())
  → 模型自行决定是否 tool_calls
```

与 [tools.md](./tools.md) 同一条 ReAct 环；只是工具实现变成了检索器。[src: LangGraph Agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag)

### 2.1 怎么跑

```bash
# 词法向量（默认，无需 embedding 模型）
poetry run python -m agent.rag_demo

# 真语义（需 ollama pull nomic-embed-text）
RAG_EMBEDDINGS=ollama poetry run python -m agent.rag_demo

poetry run pytest tests/test_rag.py -q
```

`import agent.graph` / `build_agent` 会侧效加载 `agent.rag`，默认注册词法版 `retrieve_policy`。

### 2.2 和 MCP `lookup_docs` 的差别

| | `retrieve_policy`（RAG） | MCP `lookup_docs` |
|---|---|---|
| 查找方式 | 向量相似（语义/词法） | 主题键精确匹配 |
| 进程 | 与 Agent 同进程 | 独立 MCP Server |
| 用途 | 教 Agentic RAG | 教 MCP 发现/跨进程 |

二者可同时存在；不要混为一谈。

---

## 3. 经典流水线 vs Agentic

| 模式 | 行为 | 何时用 |
|---|---|---|
| 固定 Retrieve→Generate | 每问必搜 | FAQ、要稳定延迟 |
| Agentic（本仓） | 模型决定是否/何时搜 | 混合闲聊+政策；可多跳 |

---

## 4. 和 Tool / Function Calling / MCP 的边界

| 层 | 解决什么 |
|---|---|
| RAG | 答案如何接地外部文档 |
| `tool_calls` | 模型如何发起「去检索」 |
| ToolNode | Host 如何执行并写回 `ToolMessage` |
| MCP | 检索服务是否可在别的进程被发现/调用 |

---

## 5. Embedding 两种后端

| `embeddings=` | 依赖 | 说明 |
|---|---|---|
| `"lexical"`（默认） | 无 | `LexicalBagEmbedding`：字符 bigram 哈希；hands-on/单测 |
| `"ollama"` | 本机 Ollama + `nomic-embed-text` | 真语义向量 |
| 任意 `Embeddings` 实例 | 调用方自备 | 测试可注入 |

向量库存 `InMemoryVectorStore`（进程内、不持久化）。[src: langchain-core InMemoryVectorStore]

---

## 6. 安全与质量

1. 检索片段会进上下文——注意提示注入与机密。  
2. RAG 不自动消灭幻觉——本仓要求 demo prompt 引用 `chunk_id`。  
3. Agentic 可能漏搜——政策场景靠 system 约束；生产可加强制工具/流水线兜底。

---

## 7. 代码锚点

| 主题 | 路径 |
|---|---|
| 切块 / 建库 / 注册工具 | [`agent/rag.py`](../agent/rag.py) |
| 语料 | [`agent/rag_data/`](../agent/rag_data/) |
| 交互演示 | [`agent/rag_demo.py`](../agent/rag_demo.py) |
| 单测 | [`tests/test_rag.py`](../tests/test_rag.py) |

---

## 8. 证据

- [src: docs.langchain.com LangGraph Agentic RAG] 检索作 tool  
- [src: langchain OllamaEmbeddings + InMemoryVectorStore] 官方索引/检索示例  
- [src: langchain_core.tools.retriever.create_retriever_tool] 包装为 BaseTool  
- [src: 本仓] `agent/rag.py` · `rag_data/` · `rag_demo.py` · `tests/test_rag.py`
