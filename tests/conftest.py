"""各测试模块共用的 pytest fixture。"""

import pytest

from tests.fakes import AlwaysToolLLM, FakeLLM


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def llm_that_always_calls_tool():
    return AlwaysToolLLM()
