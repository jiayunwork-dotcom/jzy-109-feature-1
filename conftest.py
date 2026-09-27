"""使 pytest 从仓库根目录运行时能 import app；并隔离电桥档全局状态。"""
import pytest

from app.main import store


@pytest.fixture(autouse=True)
def _clear_presets():
    store.clear()
    yield
    store.clear()
