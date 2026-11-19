# LangGraph + Ollama Agent 实战

用本地 Ollama（`qwen2.5:14b`）跑通一套最小但具备生产形状的 Agent：ReAct 循环、Function Calling、短期记忆、死循环熔断、上下文压缩、可观测性、MCP 工具集成、评估闭环。

> 终端：macmini（Mac17,16 · M5 Pro · 64GB · IP 192.168.1.109）· 工作区 `01-active/work_notes/ai-agents/`
> 版本（源码读签名确认，2026-11-17）：langgraph **1.2.22** / langchain **1.5.0** /
> langchain-core 1.8.1 / langchain-ollama 1.1.0 / langchain-mcp-adapters / Python 3.12.14

**分支约定**：提交纪律以 WorkSpace `AGENTS.md`「Git Flow 闸门」+ skill `git-flow` 为准。  
**消息协议**：`HumanMessage` / `AIMessage` / `ToolMessage` 等角色与状态约定见 [docs/消息协议.md](./docs/消息协议.md)。

---

## 1. 覆盖的知识点

| 知识点 | 本项目中的实现 |
|---|---|
| ReAct / Function Calling | `create_agent` + tools；模型发出 tool call，图里的 ToolNode 执行 |
| 短期记忆 | `MemorySaver` + `thread_id` 做会话隔离 |
| 死循环熔断 | `config.recursion_limit`，超限抛 `GraphRecursionError` |
| 上下文压缩 | `SummarizationMiddleware`；另有 `TraceHook._compact` 做裁剪 |
| 可观测性 | `@before_model` middleware 每次调模型前写 JSONL |
| MCP | 独立进程 stdio 服务 + 运行时 `tools/list` 发现，可与本地 `@tool` 混用 |
| 评估闭环 | 黄金集 + 确定性检查 + 可选 LLM-as-judge |

---

## 2. 目录与职责

```
langgraph-ollama-hands-on/
├── agent/
│   ├── graph.py       # Agent 工厂：模型 + 工具 + 记忆 + 中间件
│   ├── tools.py       # 进程内工具：计算器 / 天气
│   ├── demo.py        # 交互 CLI（stream 观察 ReAct 步骤）
│   ├── mcp_server.py  # FastMCP 服务（stdio，独立进程）
│   ├── mcp_client.py  # 连接 MCP、运行时发现工具
│   ├── mcp_demo.py    # 本地工具 + MCP 工具混合 Agent
│   ├── eval.py        # 黄金集 + 确定性检查 / LLM-judge
│   └── eval_run.py    # 真 Agent 跑评估
├── tests/             # 15 单元 + 1 真 Ollama 集成
├── traces/            # 运行产生的 JSONL 轨迹
├── docs/
│   └── 消息协议.md    # HumanMessage 等消息类型与 Agent 状态协议
└── README.md
```

数据流：

```
用户输入
  → create_agent 图（agent 节点 ↔ tools 节点）
  → 可选：MCP 跨进程工具 / MemorySaver 按 thread 记状态
  → middleware：trace 落盘 + 消息过多时摘要
  → 最终 AI 回复 / eval 检查
```

---

## 3. 核心模块与知识点说明

### `tools.py` — Tool 定义与安全边界

- `calculator`：用 `ast` 白名单解析算术表达式，不使用 `eval`/`exec`。
- `get_weather`：离线 fixture（北京/上海），不依赖外网 API。
- **知识点**：`@tool` 从 docstring + 类型注解生成 JSON Schema 给模型看；模型只发出结构化调用请求，真正执行在图侧 ToolNode，这是安全边界。

### `graph.py` — Agent 装配

1. `create_agent`：LangChain 1.x 官方 API（旧 `create_react_agent` 已弃用）。
2. `MemorySaver`：短期/会话记忆；不同 `thread_id` 状态隔离，可用 `get_state` 回放。
3. middleware：
   - `make_trace_middleware`：`@before_model` 写 JSONL（替代旧 `pre_model_hook`）
   - `SummarizationMiddleware`：消息数达阈值时摘要压缩（`trigger` / `keep`）
4. `build_default_agent()`：接本地 Ollama `http://127.0.0.1:11434`，默认 trace → `traces/agent.jsonl`。

测试可注入 FakeLLM；正式跑通入口是 `build_default_agent`。

### `demo.py` — 交互与流式可观测

- `--thread` 指定会话；`recursion_limit=15` 限制工具循环步数。
- `stream(..., stream_mode="updates")` 逐步输出 `[tool]` / `[ai]`，对应 Thought → Action → Observation。

### MCP 三件套

| 文件 | 作用 |
|---|---|
| `mcp_server.py` | FastMCP：暴露 `lookup_docs`（退款/配送政策） |
| `mcp_client.py` | `MultiServerMCPClient` 用 stdio 拉起 server，`get_tools()` 动态发现 |
| `mcp_demo.py` | 本地 `@tool` + MCP 工具同图；入口用 `ainvoke`（MCP 工具 async-only） |

**知识点**：

- **Function Calling**：模型请求调用工具的机制（发 tool call）。
- **MCP**：跨进程工具发现与调用的协议（stdio / HTTP 等）。
- 二者可组合：同一 Agent 图里可以同时有进程内工具和 MCP 工具。

### `eval.py` + `eval_run.py` — 评测

- 黄金集：`calc_basic`、`weather_lookup`（期望工具名、参数、答案子串）。
- **确定性层**：检查是否调对工具、参数（空白归一化）、答案是否含关键字。
- **LLM-judge 层**：对开放性回答打 0–1 分；与确定性层分开，避免主观噪声掩盖功能回归。
- `eval_run` 用真 Agent 跑，trace 写到 `traces/eval_trace.jsonl`。

---

## 4. 模块 ↔ 知识点对照

| 文件 / 机制 | 知识点 | 实现要点 |
|---|---|---|
| `agent/tools.py` | Tool schema、执行边界、参数安全 | docstring + 类型 → schema；ast allow-list，禁止裸 `eval` |
| `agent/graph.py` | ReAct 图、`create_agent`、middleware | `system_prompt` + tools；压缩用 `SummarizationMiddleware` |
| `MemorySaver` + `thread_id` | 短期记忆、会话隔离 | 不同 thread 状态不串；`get_state` 可回放 |
| `config.recursion_limit` | 图递归上限 / 死循环熔断 | 必须放 config **顶层**；超限抛 `GraphRecursionError` |
| `TraceHook` / `make_trace_middleware` | 可观测性、上下文裁剪 | `@before_model` 写 JSONL；middleware 是官方扩展点 |
| `mcp_server.py` + `mcp_client.py` | MCP 协议、运行时工具发现 | stdio FastMCP；`get_tools()` 动态列出 |
| `mcp_demo.py` | 本地工具与 MCP 工具混合 | Function Calling 与 MCP 可同图；MCP 须 `ainvoke` |
| `eval.py` + `eval_run.py` | 黄金集、确定性检查、LLM-judge | 参数比对归一化空白；两层评测分离 |
| `tests/fakes.py` | Agent 测试策略 | FakeLLM 测图结构；真模型只跑 integration |

---

## 5. 测试策略

共 **16** 个测试：

- 工具正确性、记忆隔离/跨轮回忆、`recursion_limit` 熔断、trace/压缩
- MCP 发现与执行
- eval 确定性检查 / judge 解析
- **1 个** `@pytest.mark.integration`：真连 Ollama；日常可 `-m 'not integration'`

`tests/fakes.py`：图结构与熔断用 FakeLLM / AlwaysToolLLM；真模型只做集成测试。

---

## 6. 快速开始

前提：本机已装 [Poetry](https://python-poetry.org/)（≥2.x）；Ollama 在 `11434` 且已有 `qwen2.5:14b`（纯单元测试可不启）。

```bash
cd /path/to/langgraph-ollama-hands-on
poetry install                                          # 按 poetry.lock 建 .venv 并装依赖（含 dev/pytest）
poetry run python -m pytest -q                          # 全部 16 测试（15 单元 + 1 真 Ollama 集成）
poetry run python -m pytest -m 'not integration' -q     # 只跑 15 个单元测试（不需 Ollama）
poetry run python -m agent.demo --thread demo           # 交互式：记忆 + 工具 + stream 可观测
poetry run python -m agent.mcp_demo                     # MCP：独立进程工具动态发现 + 混合调用
poetry run python -m agent.eval_run                     # 黄金集评估（真 agent 跑真 case）
```

依赖由 **Poetry** 管理：`pyproject.toml` 声明版本，`poetry.lock` 锁定解析结果；虚拟环境默认在项目内 `.venv/`（见 `poetry.toml`）。增删依赖用 `poetry add` / `poetry add -G dev`，再提交更新后的 lock。

---

## 7. 总结

本仓是一套可跑的 LangGraph Agent 骨架：记忆、工具、熔断、trace、MCP、评测都齐，代码量小（`agent/` 约 500 行），对齐官方 1.x API，并记录真实踩坑，方便对照源码理解上述知识点。

---

## 证据 / 来源

- LangChain `create_agent` / `SummarizationMiddleware` / MCP adapter 签名：读自已装包源码 `inspect.signature`（2026-11-17）
- [LangGraph Memory 官方指南](https://github.com/langchain-ai/langgraphjs/blob/c9e96aa500ac6c6c3410dd45bdf02bc9c1738503/docs/docs/agents/memory.md)
- [GRAPH_RECURSION_LIMIT 官方说明](https://reference.langchain.com/python/langgraph/errors/ErrorCode/GRAPH_RECURSION_LIMIT)
- [ChatOllama integration 文档](https://docs.langchain.com/oss/python/integrations/chat/ollama)
- [LangChain Agents 官方文档](https://docs.langchain.com/oss/python/langchain/agents)
