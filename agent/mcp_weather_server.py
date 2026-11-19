"""Weather MCP Server：共享天气能力的独立进程示例。

演示「一个 Weather Server，多个 Host 去连」（见 docs/mcp.md §4）。
数据真源：`weather_fixture.py`（与进程内 get_weather 相同）。

    poetry run python -m agent.mcp_weather_server
"""

from mcp.server.fastmcp import FastMCP

from agent.weather_fixture import lookup_weather

mcp = FastMCP("hands-on-weather")


@mcp.tool()
def get_weather(city: str) -> str:
    """查询某城市今日天气。离线演示数据：北京 / 上海。

    Args:
        city: 中文城市名，例如 "北京"。
    """
    return lookup_weather(city)


if __name__ == "__main__":
    mcp.run(transport="stdio")
