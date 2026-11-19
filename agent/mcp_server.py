"""本地 FastMCP 服务，用于演示 MCP 工具接入。

直接以 stdio 运行，供 Agent 消费：
    .venv/bin/python -m agent.mcp_server

政策文案真源：`agent/policy_snippets.py`（与 rag_data 对齐的短摘要）。
"""

from mcp.server.fastmcp import FastMCP

from agent.policy_snippets import POLICY_BY_TOPIC

mcp = FastMCP("hands-on-docs")


@mcp.tool()
def lookup_docs(topic: str) -> str:
    """按主题查询内部政策知识库（键值查找，非向量检索）。

    Args:
        topic: 'refund' / 'shipping' / 'warranty' 之一。
    """
    key = topic.lower().strip()
    return POLICY_BY_TOPIC.get(key, f"未找到主题：{topic}（可选：{', '.join(POLICY_BY_TOPIC)}）")


if __name__ == "__main__":
    mcp.run(transport="stdio")
