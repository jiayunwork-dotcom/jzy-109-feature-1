"""电桥档：命名桥臂配置的登记与检索。

进程内存实现：运行期间可把常用四臂配置命名成档反复调用，跨重启
不保留。每档保存的是不可变的 ArmSet，档与档之间完全独立——一套
档的阻值不会串到另一套名下。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from app.bridge.topology import ArmSet


@dataclass(frozen=True)
class Preset:
    name: str
    arms: ArmSet
    description: str | None = None


class PresetStore:
    """线程安全的内存登记处。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._presets: dict[str, Preset] = {}

    def register(self, name: str, arms: ArmSet, description: str | None = None) -> Preset:
        """登记新档或整体替换同名档（替换不影响任何其它档）。"""
        preset = Preset(name=name, arms=arms, description=description)
        with self._lock:
            self._presets[name] = preset
        return preset

    def get(self, name: str) -> Preset | None:
        with self._lock:
            return self._presets.get(name)

    def list(self) -> list[Preset]:
        with self._lock:
            return sorted(self._presets.values(), key=lambda p: p.name)

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._presets.pop(name, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._presets.clear()
