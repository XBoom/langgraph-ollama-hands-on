"""离线天气假数据（北京/上海）。

本地 `@tool get_weather` 与 Weather MCP Server 共用，避免两套真相。
"""

from __future__ import annotations

import json

WEATHER_FIXTURE: dict[str, dict[str, object]] = {
    "北京": {"temp_c": 21, "condition": "晴"},
    "上海": {"temp_c": 26, "condition": "多云"},
}


def lookup_weather(city: str) -> str:
    data = WEATHER_FIXTURE.get(city, {"temp_c": 20, "condition": "未知"})
    return json.dumps({"city": city, **data}, ensure_ascii=False)
