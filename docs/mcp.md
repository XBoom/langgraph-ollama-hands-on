# 什么是 MCP？它和 Tool / Function Calling 什么关系？

> 本文是**本仓库的对照说明**，讲协议与接入原理，不写「lookup_docs 政策条文」。  
> Tool 在图里怎么跑见 [tools.md](./tools.md)；检索增强见 [rag.md](./rag.md)；消息形态见 [消息协议.md](./消息协议.md)。

对齐版本：本仓 `mcp` 1.30.x · `langchain-mcp-adapters` 0.3.x · FastMCP stdio。

---

## 1. 一句话定义

**MCP（Model Context Protocol）= 主机（Host/Agent）与外部能力提供者（Server）之间的标准协议**，用来**发现、描述、调用**工具（以及资源/提示等；本仓演示聚焦 **tools**）。

它解决的不是「模型怎么发调用请求」（那是 Function Calling / `tool_calls`），而是：

> **工具实现可以不在 Agent 进程里**——跑在另一个进程/机器上，用统一协议列出清单并远程执行。

官方 tools 能力：客户端发 `tools/list` 发现；发 `tools/call` 调用；工具带 `name` / `description` / `inputSchema`。[src: MCP Tools 规范](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

---

## 2. 为什么需要 MCP？（N×M 问题）

没有标准协议时：

| 侧 | 要对接 |
|---|---|
| 每个 Agent / IDE / 聊天产品 | 各自写一套「接天气、接 DB、接内部知识库」的插件 API |
| 每个工具服务 | 为 Cursor、LangGraph、某某 Bot 各做一遍适配 |

→ **N 个宿主 × M 个工具源 = N×M 集成**。

MCP 把契约抽成一层：Server 只实现 MCP；Host 只实现 MCP Client。宿主换了、工具源换了，协议面仍通。本仓注释里的「解决 N×M 集成爆炸 / 工具动态发现」指的就是这个。

---

## 3. 和普通 API（REST/RPC）差在哪？

先分清角色（搞反就会觉得「每个 Agent 都是 MCP 服务器」）：

| 角色 | 是谁 | 干什么 |
|---|---|---|
| **MCP Server** | 能力提供方（天气服务、知识库、本仓 `mcp_server.py`） | 实现 `tools/list` / `tools/call` |
| **MCP Client / Host** | 使用方（Cursor、Claude Desktop、本仓 LangGraph Agent） | **配置并连接**若干 Server，把发现到的工具交给模型 |

**天气能力应做成「一个 Weather MCP Server」**；Agent1 / Agent2 若只是聊天产品，它们通常是 **Client（宿主）**，不是每人再开一个天气 Server。

### 3.1 对比一张表

| | 普通业务 API | MCP |
|---|---|---|
| 契约长什么样 | 各家路径/字段不同（`/v1/weather` vs `/api/forecast`） | **对话语法**统一：`tools/list`、`tools/call` + JSON Schema（见下节：不是统一成一个域名） |
| 宿主怎么接 | 为每个 API **写专用客户端代码** | 宿主实现 **一次** MCP Client；新能力多半是 **加一条 Server 配置** |
| 模型怎么用 | API 不会自动变成 tool；要你手写包装成 `@tool` | Client `get_tools()` 后即可 `bind_tools` / 进 `create_agent` |
| 发现 | 靠读文档、写死 URL | 运行时 list，工具增减可动态感知（视 Server 能力） |
| 传输 | 多为 HTTP | stdio / HTTP 等；**语义仍是 list/call** |

要点：

- MCP **不是**「取代所有 HTTP」；Server **内部**照样可以调气象局 HTTP API。  
- MCP 换掉的是 **「每个宿主为每个后端写一套插件」** 这一层，换成 **标准插头**。  
- 所以：「别人要用，不用一个一个写对接代码」——指的是 **不用为 Cursor 写一版、为 LangGraph 再写一版天气 SDK**；**不是**「客户端零配置、自动看见全世界所有 Agent」。

### 3.2 「统一 tools/list」≠「全世界一个域名」

这里的「统一」指的是 **协议台词相同**，不是 **网络地址收成一个 host**。分三层看就不会混：

```text
┌─────────────────────────────────────────────────────────────┐
│ ① Host ↔ MCP Server（MCP 层）                                │
│    台词永远是：tools/list、tools/call + JSON Schema            │
│    地址：每个 Server 仍各自配置（stdio 命令 / 各自的 MCP URL）   │
├─────────────────────────────────────────────────────────────┤
│ ② MCP Server ↔ 真实业务 API（实现层，Host 看不见）              │
│    WeatherA Server → api.openweathermap.org                  │
│    WeatherB Server → api.weatherapi.com                      │
│    域名、路径、鉴权、字段名可以完全不同——被 Server 消化掉         │
└─────────────────────────────────────────────────────────────┘
```

| 问题 | 答案 |
|---|---|
| `tools/list` 怎么能「统一」？ | 统一的是 **方法名与报文形状**（怎么列工具、怎么调、参数用 JSON Schema 描述），不是统一成 `https://one.example.com`。 |
| 两家天气 API 域名不同怎么办？ | **正常**。各自（或同一个）MCP Server 内部去打不同域名；Host 只对 Server 说 `tools/call name=get_weather`。 |
| 两个 Weather MCP Server 是不是还要配两个地址？ | **要。** Host 配置里仍是两条（两个 stdio/两个 MCP URL）。省的是「为每个域名写一套 SDK」，不是「只留一个域名」。 |
| 能不能对外只暴露一个入口？ | 可以再加一层 **聚合网关 MCP Server**（一个地址，背后转发多家 API）；那是部署选择，不是协议自带「全球单域名」。 |

对照本仓：`mcp_client` 里配的是「用哪个解释器跑 `mcp_server.py`」（一条 Server 配置），不是气象局的域名——演示 Server 不打外网；`lookup_docs` 返回的是 [`policy_snippets.py`](../agent/policy_snippets.py) 短摘要（与 `rag_data` 事实对齐，查找方式仍是键值而非向量）。

### 3.3 「不用一个一个配置」到底省了什么？

| 仍要做的 | 不必再做的 |
|---|---|
| 每个 **Host** 声明连哪些 MCP Server（命令/URL 仍可**多条**） | 为每个业务域名再写一套私有 REST 客户端/字段映射 |
| Server 内部配置它要打的气象局域名与密钥 | 天气 API 厂商为每个 Agent 产品各做一遍私有插件 |

省的是 **对接语法上的 N×M 开发**，不是「全世界收成一个域名」。

---

## 4. Agent1、Agent2 都会查天气，客户端要配两个 Server 吗？

取决于 **天气实现放在哪**，不要把「Agent」默认当成 MCP Server。

### 4.1 推荐：一个共享天气 Server，两个 Agent 当 Client

```text
                    ┌─────────────────────┐
                    │ Weather MCP Server  │  ← 只部署这一份
                    │ tools: get_weather  │
                    └──────────▲──────────┘
                               │ tools/list · tools/call
              ┌────────────────┴────────────────┐
              │                                 │
     ┌────────┴────────┐               ┌────────┴────────┐
     │ Agent1 (Host)   │               │ Agent2 (Host)   │
     │ MCP Client 配置 │               │ MCP Client 配置 │
     │ → 同一 weather  │               │ → 同一 weather  │
     └─────────────────┘               └─────────────────┘
```

- Agent1、Agent2 **各自**在自己的配置里写上「连这个 Weather Server」（各一条配置）。  
- **不是**「客户端为了选 Agent 而配两个天气 Server」。  
- 终端用户若只用 Agent1，只碰 Agent1；天气 Server 对用户往往是基础设施，不是「再选一个 Agent」。

### 4.2 若 Agent1、Agent2 各自做了一个天气 MCP Server（重复建设）

那对某个要**同时**挂两个源的 Host 来说：是的，配置里会出现 **两个** Server 条目，模型（或你）再选调哪一个——这是 **重复提供方** 的问题，不是 MCP 逼你这么做。

合并成一个共享 Server，或做一个「聚合网关 Server」对外只暴露一份 `get_weather`，Client 就只需配 **一个** 地址。

### 4.3 和本仓的对应

本仓演示里：

- `mcp_server.py` = **Server**（文档工具）  
- `mcp_demo` / `mcp_client` = **Client（Host）**  
- 本地 `get_weather` 甚至还在进程内 `@tool`，**没有**做成 MCP——若做成 MCP，也应是「一个 weather server」，多个 demo/Agent 去连它。

**一句话**：MCP 让「天气」做成标准插头，**多个 Agent 共用一个插头**；不是「每个 Agent 自带一个插头，客户端再两两配置选哪个 Agent 的天气」。

---

## 5. 和「进程内 @tool」差在哪？

| | 进程内 `@tool` | MCP 工具 |
|---|---|---|
| 代码在哪 | 与 Agent **同进程** import | **独立 server 进程**（或远端服务） |
| 何时知道有哪些工具 | 定义/import 时（本仓注册表） | **运行时** `tools/list` |
| 调用怎么走 | ToolNode 直接调 Python 函数 | ToolNode 调适配后的 `BaseTool` → 协议 **`tools/call`** → server 执行 |
| 失败域 | 同进程异常 | 另有进程生命周期、stdio/网络、序列化 |

二者对 **模型** 可以长得一样：都是带 Schema 的可调用能力。差别在 **Host 如何拿到实现、如何执行**。

```text
进程内：  模型 --tool_calls--> ToolNode --直接调--> 本地函数
MCP：     模型 --tool_calls--> ToolNode --适配器--> MCP Client --tools/call--> Server 进程
```

---

## 6. 和 Function Calling / `tool_calls` 什么关系？

**正交、可组合，不是二选一。**

| 概念 | 层 | 干什么 |
|---|---|---|
| Function Calling / Tools API | **模型 ↔ Host** | 模型看 Schema，发出 `tool_calls`；Host 解析意图 |
| MCP | **Host ↔ 外部 Server** | 列出远程工具、代为执行、拿回结果 |
| LangGraph ToolNode | **图内执行器** | 不管工具来自本地还是 MCP，按 `name` 调到对应 `BaseTool` |

本仓 [`mcp_demo.py`](../agent/mcp_demo.py) 写得很直白：

> Function Calling 是模型请求调用工具的机制；MCP 是让 Agent 发现/调用「跑在另一进程里的工具」的协议。二者可组合。

同一张 `create_agent` 图里：`all_tools = [*get_tools(), *remote_tools]`——本地计算器与 MCP 知识库对模型都是 tools；执行路径在适配器之后才分叉。  
本仓 `lookup_docs` 只是键值「假知识库」，**形态上**像 Agentic RAG 的「检索当 Tool」，但不是向量检索；边界见 [rag.md](./rag.md)。

---

## 7. 协议里和本仓相关的两步

### 7.1 发现：`tools/list`

Client → Server：列出当前可用工具（可分页）。每项至少含：

- `name`：唯一标识  
- `description`：给人/模型看何时用  
- `inputSchema`：参数 JSON Schema  

本仓：[`discover_mcp_tools`](../agent/mcp_client.py) 用 `MultiServerMCPClient(...).get_tools()`；适配器在内部完成 list，并把结果**转成 LangChain `BaseTool`**，这样就能塞进 `create_agent(tools=...)`。

### 7.2 调用：`tools/call`

Client → Server：`name` + `arguments`。  
Server 返回 **content 块列表**（常见 `{"type":"text","text":"..."}`），不是保证纯字符串。[src: MCP tools/call](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

本仓测试断言：适配后的工具结果是 content blocks，需拼 `text` 再断言（见 [`tests/test_mcp.py`](../tests/test_mcp.py)）。

---

## 8. 传输：本仓为什么是 stdio？

MCP 可跑在多种传输上（stdio、HTTP/SSE 等）。本仓演示选 **stdio**：

1. Client 用当前解释器拉起 `agent/mcp_server.py`。  
2. 父子进程用标准输入/输出交换 JSON-RPC。  
3. 无需另起端口；关掉 Agent 侧连接，server 进程随之结束（典型本地开发形态）。

[`mcp_server.py`](../agent/mcp_server.py) 入口：`mcp.run(transport="stdio")`。  
生产常见再加远程 HTTP MCP；**协议语义（list/call）不变，变的是管道**。

```text
Agent 进程                         Server 进程
┌─────────────────────┐           ┌──────────────────┐
│ MultiServerMCPClient│  stdio    │ FastMCP           │
│  get_tools()        │◄────────►│  @mcp.tool()      │
│  tool.ainvoke(...)  │  JSON-RPC │  lookup_docs ...  │
└─────────────────────┘           └──────────────────┘
```

---

## 9. 怎样进到 LangGraph 环里？

MCP **不替换** ReAct 图；它只是 **tools 列表的另一种货源**。

```text
discover_mcp_tools()  →  list[BaseTool]   # 运行时
get_tools()           →  list[BaseTool]   # 本地注册表
        \             /
         all_tools = 合并
              │
              ▼
     create_agent(tools=all_tools, ...)
              │
              ▼
     模型 bind_tools（看见全部 Schema）
              │
     有 tool_calls → ToolNode
              │
     若是 MCP 适配工具 → 异步 tools/call → ToolMessage
```

与 [tools.md](./tools.md) 同一条安全边界：**模型仍只发 `tool_calls`；执行仍在图侧**——只是「图侧」对 MCP 工具意味着「经 Client 打到 Server」。

---

## 10. 工程坑（原理连带后果）

| 现象 | 原因 |
|---|---|
| `.invoke()` 失败 / `NotImplementedError` | `langchain_mcp_adapters` 常把 MCP 工具做成 **仅 async** 的 `StructuredTool`；须 **`ainvoke` / `agent.ainvoke`**（本仓 `mcp_demo`、单测均如此） |
| 返回值不是 `str` | MCP 结果是 **content blocks**；写评测/日志要按块取 `text` |
| 远端工具不在本地 `get_tools()` | 本地注册表只收进程内 `@tool`；MCP 列表要另 `discover_*` 再合并（或再 `register_tool`） |
| server 没起来就调 | stdio 由 Client 拉起；路径/`sys.executable` 错会导致发现失败 |

---

## 11. 本仓对照（落点，非功能说明书）

| 原理点 | 本仓落点 |
|---|---|
| MCP Server 暴露工具 | [`agent/mcp_server.py`](../agent/mcp_server.py) FastMCP + `@mcp.tool()` |
| Client 发现 + 适配为 BaseTool | [`agent/mcp_client.py`](../agent/mcp_client.py) `MultiServerMCPClient` |
| 与本地工具同图 | [`agent/mcp_demo.py`](../agent/mcp_demo.py) `[*get_tools(), *remote_tools]` |
| 发现 / async 执行断言 | [`tests/test_mcp.py`](../tests/test_mcp.py) |

先跑：

```bash
poetry run python -m agent.mcp_demo
# 或
poetry run pytest tests/test_mcp.py -q
```

---

## 12. 证据

- [src: modelcontextprotocol.io Tools] `tools/list` / `tools/call`、`inputSchema`、content blocks  
- [src: 本仓 mcp_client 模块注释] 构建时 import vs 运行时发现  
- [src: 本仓 mcp_demo 模块注释] Function Calling 与 MCP 正交可组合  
- [src: langchain-mcp-adapters + 本仓 test_mcp] 适配为 BaseTool；执行偏 async；结果为 content blocks
