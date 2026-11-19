# 什么是 Tool？它在 LangGraph 里怎么跑？

> 本文是**本仓库的对照说明**，讲概念与执行原理，不写「本仓 calculator 干什么」。  
> 协议细节（`tool_calls` ↔ `ToolMessage`）见 [消息协议.md](./消息协议.md)。  
> 跨进程工具发现/调用见 [mcp.md](./mcp.md)。

对齐版本：langchain-core 1.8.x / langchain `create_agent`（本仓封装在 [`agent/graph.py`](../agent/graph.py)）。

---

## 1. 一句话定义

**Tool = 给模型看的「可调用能力说明书」+ 给运行时执行的「真函数」。**

拆开看：

| 侧面 | 是什么 | 谁消费 |
|---|---|---|
| 说明书 | `name`、`description`、参数 JSON Schema | **模型**：决定「要不要调、调哪个、填什么 args」 |
| 真函数 | Python 可调用对象（`BaseTool` / `@tool` 包出来的） | **图里的 tools 节点**：按 `tool_calls` 真正执行 |

模型**不会**跑你的函数体；它只输出结构化调用意图。执行权永远在图侧。

官方表述：tools 是带明确输入输出的可调用对象，传给 chat model；模型据对话上下文决定是否调用、传什么参数。[src: LangChain Tools 文档](https://docs.langchain.com/oss/python/langchain/tools)

---

## 2. 为什么需要 Tool？（相对「纯聊天」）

纯 LLM 只有训练分布里的知识与推理；要**算准、查实时、改外部系统**，就必须走出模型权重，落到外部动作。

Tool 把「外部动作」标准化成：

1. 模型可读的契约（Schema + 描述）  
2. 可重复执行的实现（你的代码 / MCP 远端）  
3. 可写回对话的观察结果（`ToolMessage`）

没有这三步，就只是「模型嘴上说调用了」，没有可验证的 Observation。

---

## 3. 在 LangGraph / `create_agent` 里的位置

本仓用 `langchain.agents.create_agent`；它在底层编成一张 **LangGraph 状态图**，核心是 ReAct 环：Thought → Action → Observation 循环，直到模型不再发 `tool_calls`。[src: create_agent 文档](https://reference.langchain.com/python/langchain/agents/factory/create_agent)

### 3.1 两个关键节点

```text
                    ┌──────────────────────┐
                    │  model（调 LLM）      │
                    │  输入: messages       │
                    │  输出: AIMessage      │
                    └──────────┬───────────┘
                               │
              有 tool_calls？   │   没有 → 结束（最终回答）
                               ▼
                    ┌──────────────────────┐
                    │  tools（ToolNode）    │
                    │  按 name 找实现并执行 │
                    │  追加 ToolMessage(s) │
                    └──────────┬───────────┘
                               │
                               └──► 再回 model
```

- **model 节点**：把当前 `messages`（通常已带 system）发给 LLM；若响应含 `tool_calls`，图走向 tools。  
- **tools 节点**：预置 `ToolNode`（或等价逻辑）：对每条 `tool_call` 按 `name` 查表执行，把返回值写成 `ToolMessage`，`tool_call_id` 必须对齐调用方的 `id`。

本仓流式观察节点名：`demo` 里 `stream_mode="updates"` 打印的是 `model` / `tools`（见 [`agent/demo.py`](../agent/demo.py)）。

### 3.2 挂载发生在建图时

```python
create_agent(model=llm, tools=tool_list, system_prompt=...)
```

`tools=` 做了两件相关的事：

1. **给模型绑定能力清单**（bind tools / 等价机制）：推理时能看到有哪些 name、参数长什么样。  
2. **给 ToolNode 注册实现表**：运行时才能把 `name` 映射到真函数。

只写进 prompt 文字、却不传 `tools=`，模型可能「口头想调」，图侧没有执行器；只传实现、模型却未绑定 Schema，则经常调不起来或乱填参。两边要一致。本仓 [`build_agent`](../agent/graph.py) 用同一份 `tool_list` 既交给 `create_agent`，也喂给 `compose_system_prompt`（额外自然语言清单，是提示增强，**不能替代** Schema 绑定）。

### 3.3 状态怎么长

状态核心仍是 `messages`（`add_messages` 追加）。一轮典型工具回合：

```text
HumanMessage
  → AIMessage(tool_calls=[{id, name, args}])   # Action：意图
  → ToolMessage(tool_call_id=同一 id, content=…) # Observation：事实
  → AIMessage(content=最终回答)                 # 综合后的答复
```

同一轮可有多条 `tool_calls`；tools 节点可并行执行多条（实现细节随 LangGraph / ToolNode 版本）。循环次数受 `recursion_limit` 等约束（本仓 demo 已设）。

---

## 4. Tool 对象内部有什么？

从「函数」到「Tool」：

```python
@tool
def foo(x: str) -> str:
    """一句话：模型靠这个决定何时调用。"""
    ...
```

装饰器（LangChain `@tool`）大致产出：

| 字段 | 来源 | 用途 |
|---|---|---|
| `name` | 函数名（可覆盖） | `tool_calls[].name` 的查找键 |
| `description` | docstring | 模型选型依据 |
| `args_schema` | 类型注解 + Args 文档 | 约束 / 提示参数形状 |
| 可调用体 | 函数本身 | ToolNode 真正执行 |

**关键分工**：Schema 是给模型的接口合同；函数体是给运行时的实现。改 docstring / 注解会影响「模型怎么选」；改函数体影响「世界怎么变」。

---

## 5. JSON Schema：何时生成？模型在哪里看见？

README 里那句「`@tool` 从 docstring + 类型注解生成 JSON Schema 给模型看」容易误解成「写进 prompt 正文」。实际分两段。

### 5.1 何时生成？

在 **`@tool` 装饰函数时**（import / 定义模块时），不是每次用户提问才现算。

LangChain 从类型注解 + docstring 推断 Pydantic `args_schema`，挂在 `BaseTool` 上。之后可随时导出 JSON Schema，例如：

```python
calculator.args_schema.model_json_schema()
# properties.expression.type == "string"；description 来自 docstring
```

**生成时机 = 造 Tool 对象时**；请求模型时主要是序列化/转换已有 schema，不是重新读源码。

### 5.2 在哪里给模型看？

**不是**主要靠 system prompt 里「可用工具：…」。那是本仓 `compose_system_prompt` 的自然语言补强，可有可无，**不能替代** Schema 绑定。

真正让模型能发出合规调用的路径：

1. `create_agent(..., tools=tool_list)` 建图。  
2. 每次进 **model 节点**调 LLM 前，`create_agent` 内部对模型做 **`bind_tools(final_tools)`**（langchain `agents/factory.py`）。  
3. 本仓 `ChatOllama.bind_tools` 用 `convert_to_openai_tool(tool)` 转成 OpenAI 风格函数定义，例如：

```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "安全求值算术表达式…",
    "parameters": {
      "type": "object",
      "properties": { "expression": { "type": "string" } },
      "required": ["expression"]
    }
  }
}
```

4. 这些定义作为 **本次聊天 API 请求的 `tools` 字段**（与 `messages` 并列）发给 Ollama/模型，**不是**塞进某条 `HumanMessage` 正文，也不是 ToolNode 在展示。

模型据此决定是否调用、填什么 `args`，再吐出结构化 `tool_calls`；图侧 `ToolNode` 按 `name` 执行真函数。

| 问题 | 答案 |
|---|---|
| 何时生成 Schema？ | `@tool` 时写入 `args_schema`；请求前再 `convert_to_openai_tool` |
| 在哪里给模型看？ | 每次 model 调用的请求参数 **`tools`**（经 `bind_tools`） |
| system 工具清单？ | 额外提示，不能替代 `bind_tools` |

---

## 6. 为什么文档/代码里几乎看不到「function call」？

口语里的 **Function Calling**（函数调用能力）和协议字段名 **`function_call` / `FunctionMessage`** 不是一回事。本仓用的是**现行 Tools 协议**，所以表面上看「没有 func call」。

### 6.1 能力还在，字段改名了

| 年代 / 说法 | 请求侧 | 模型输出 | 工具结果消息 |
|---|---|---|---|
| 旧 OpenAI Functions API | `functions` + `function_call` | 单条 `function_call` | 常对应 `FunctionMessage` |
| 现行 Tools API（本仓） | **`tools`** +（可选）`tool_choice` | **`tool_calls`（可多条）** | **`ToolMessage`** + `tool_call_id` |

业界把「让模型结构化点名外部函数」仍叫 function calling；实现上 OpenAI 等已把主路径迁到 **tools / tool_calls**。LangChain / LangGraph / `create_agent` / Ollama 的 `bind_tools` 跟的是这条新路径。

因此：

- demo 打印的是 `[ai] tool_calls=...`，不是 `function_call=...`。  
- 状态里挂的是 `ToolMessage`，不是 `FunctionMessage`。  
- API 载荷里虽仍可能出现 `"type": "function"`（表示「这是一个可调用函数定义」），那是 **tool 条目的类型标签**，不等于旧版 `function_call` 字段。

### 6.2 本仓为何不用 FunctionMessage？

`FunctionMessage` 是旧协议遗留类型。本仓 traces **刻意跳过**它（见 `graph.py` 序列化与 [消息协议.md](./消息协议.md)）：现行 ReAct 环只认 `AIMessage.tool_calls` ↔ `ToolMessage`。再写 `FunctionMessage` 既不会被 `ToolNode` 按新契约消费，也会和 checkpointer 里的消息形状打架。

**结论**：不是没做函数调用；是 **Function Calling 能力 = 现行的 tools + tool_calls + ToolMessage**。找 `function_call` 字段会落空，应看 `tool_calls`。

---

## 7. 和控制流的关系（Workflow vs Agent）

| 模式 | 工具何时跑 | 典型用法 |
|---|---|---|
| 固定 Workflow | 你写死边：某节点后必调某工具 | 流水线、确定性步骤 |
| Agent（本仓） | **模型决定**下一步是否 `tool_calls` | 开放问答、可选工具 |

本仓是后者：图只提供「能调哪些工具 + 怎么执行 + 怎么写回消息」；**是否调用、调用顺序、参数内容**由模型在环里动态决定。这就是「agentic」相对「硬编码 workflow」的差异。[src: LangGraph workflows-agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)

手写图时，等价积木是：`ToolNode([...])` 当节点 + 条件边「最后一条 AIMessage 是否有 `tool_calls`」。`create_agent` 把这套装好了。

---

## 8. 安全与信任边界（原理层）

```text
不可信：用户自然语言、模型生成的 args
可信任执行面：你的 Tool 实现（白名单、校验、权限）
```

因此：

1. **永远在图侧执行**，不要假设「模型说算完了」等于真相。  
2. **args 是数据，不是代码**：禁止把用户/模型字符串直接 `eval`/`exec`。  
3. **Schema 不是沙箱**：它只约束形状，不保证语义安全；危险操作要在函数里再鉴权 / 限流。  
4. **Observation 会回灌上下文**：工具返回值下一轮模型看得见——勿把密钥、原始 PII 原样塞进 `ToolMessage`。

---

## 9. 本仓对照（实现落点，非功能说明书）

| 原理点 | 本仓落点 |
|---|---|
| 建图时传入 tools | `build_agent` → `create_agent(..., tools=tool_list)` |
| Schema → 模型 | `bind_tools` → `convert_to_openai_tool` → 请求字段 `tools` |
| 模型↔工具环 | `demo` stream 的 `model` / `tools`；看 `tool_calls` 而非旧 `function_call` |
| Tool 定义 | `agent/tools.py`（`@tool` → `BaseTool`） |
| 消息契约 | [消息协议.md](./消息协议.md) §4 |
| 假模型如何发 `tool_calls` | `tests/fakes.py` |

本仓额外用注册表 + `get_tools()`，避免手维护全局列表；那是**工程便利**，不改变上述 LangGraph 原理：最终仍是「一份 `tools` 列表进 `create_agent`」。

---

## 10. 证据

- [src: docs.langchain.com/oss/python/langchain/tools] Tool = 可调用 + Schema，模型决策、运行时执行  
- [src: create_agent reference] model 有 `tool_calls` → tools 节点 → `ToolMessage` → 再调 model，直到无 `tool_calls`  
- [src: langchain_ollama ChatOllama.bind_tools] `convert_to_openai_tool` 写入请求 `tools`  
- [src: LangGraph ToolNode / workflows-agents] 手写图时的执行积木  
- [src: 本仓] `agent/graph.py` · `agent/demo.py` · `agent/tools.py`；traces 跳过 `FunctionMessage`
