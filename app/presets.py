"""电桥档：命名桥路配置的登记与检索。

进程内存实现：运行期间可把常用配置命名成档反复调用，跨重启不保留。
一档保存的是不可变配置对象（四臂 :class:`ArmSet` 或双电桥
:class:`KelvinConfig`），档与档之间完全独立。每档带 ``bridge_type``：
``wheatstone``（四臂惠斯通电桥，老式无类型登记请求的默认值）或
``kelvin``（开尔文双电桥）。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from app.bridge.kelvin_topology import KelvinConfig
from app.bridge.topology import ArmSet

#: 电桥类型常量
WHEATSTONE = "wheatstone"
KELVIN = "kelvin"
BRIDGE_TYPES = (WHEATSTONE, KELVIN)

#: 老式登记请求不带类型时按此处理
DEFAULT_BRIDGE_TYPE = WHEATSTONE

#: 一档配置对象的联合类型（仅作文档说明）
BridgeConfig = ArmSet | KelvinConfig


@dataclass(frozen=True)
class Preset:
    name: str
    config: BridgeConfig
    bridge_type: str = WHEATSTONE
    description: str | None = None

    @property
    def arms(self) -> ArmSet:
        """四臂配置（仅 ``bridge_type == 'wheatstone'`` 时有意义）。"""
        if not isinstance(self.config, ArmSet):
            raise AttributeError("该电桥档不是四臂惠斯通电桥")
        return self.config


class PresetStore:
    """线程安全的内存登记处。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._presets: dict[str, Preset] = {}

    def register(self, name: str, preset_or_arms, description: str | None = None) -> Preset:
        """登记新档或整体替换同名档（替换不影响任何其它档）。

        兼容两种调用：
        - ``register(name, preset)``：传入完整 :class:`Preset`；
        - ``register(name, arms, description=None)``：传入四臂
          :class:`ArmSet`（历史签名，按 wheatstone 档处理）。
        """
        if isinstance(preset_or_arms, Preset):
            preset = preset_or_arms
        else:
            preset = Preset(
                name=name,
                config=preset_or_arms,
                bridge_type=WHEATSTONE,
                description=description,
            )
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
