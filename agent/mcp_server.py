"""本地 FastMCP 服务，用于演示 MCP 工具接入。

直接以 stdio 运行，供 Agent 消费：
    .venv/bin/python -m agent.mcp_server
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hands-on-docs")


# 内存里的小「知识库」，以 MCP 工具暴露。重点不在数据本身，
# 而在于工具跑在独立进程/服务里，Agent 通过 MCP 协议运行时动态发现
#（对比进程内 @tool）。
_DOCS = {
    "refund": "退款政策：7 天无理由，需保持商品完好，运费由买家承担。",
    "shipping": "配送政策：满 99 包邮，通常 2-3 天送达。",
}


@mcp.tool()
def lookup_docs(topic: str) -> str:
    """按主题查询内部政策知识库。

    Args:
        topic: 'refund' 或 'shipping' 之一。
    """
    return _DOCS.get(topic.lower(), f"未找到主题：{topic}")


if __name__ == "__main__":
    mcp.run(transport="stdio")
