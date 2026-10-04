"""电桥档：命名电桥配置的登记与检索。

进程内存实现：运行期间可把常用配置命名成档反复调用，跨重启不保留。档分
两种类型，类型在登记时钉死：

* ``wheatstone``（四臂惠斯通电桥）：载荷是 :class:`ArmSet`；
* ``kelvin``（开尔文双电桥）：载荷是 :class:`KelvinBridge` 及恒流源电流。

老式登记请求（不带类型）一律按 ``wheatstone`` 处理。每档保存不可变载荷，
档与档之间完全独立——一套档的阻值不会串到另一套名下。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Union

from app.bridge.kelvin_topology import KelvinBridge
from app.bridge.topology import ArmSet

#: 电桥类型常量
WHEATSTONE = "wheatstone"
KELVIN = "kelvin"
BRIDGE_TYPES: tuple[str, ...] = (WHEATSTONE, KELVIN)

#: 各类型保存的载荷（arms 或 kelvin 参数）
BridgeLoad = Union[ArmSet, KelvinBridge]


@dataclass(frozen=True)
class Preset:
    name: str
    arms: ArmSet | None = None
    description: str | None = None
    type: str = WHEATSTONE
    kelvin: KelvinBridge | None = None
    source_current: float | None = None

    @property
    def load(self) -> BridgeLoad:
        """该档的电桥参数载荷（按类型取）。"""
        return self.kelvin if self.type == KELVIN else self.arms  # type: ignore[return-value]


class PresetStore:
    """线程安全的内存登记处。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._presets: dict[str, Preset] = {}

    def register(self, name: str, arms: ArmSet, description: str | None = None) -> Preset:
        """登记/替换一套四臂惠斯通电桥档（老式用法，类型固定 wheatstone）。"""
        preset = Preset(name=name, arms=arms, description=description, type=WHEATSTONE)
        with self._lock:
            self._presets[name] = preset
        return preset

    def register_kelvin(
        self,
        name: str,
        bridge: KelvinBridge,
        source_current: float,
        description: str | None = None,
    ) -> Preset:
        """登记/替换一套开尔文双电桥档。"""
        preset = Preset(
            name=name,
            arms=None,
            description=description,
            type=KELVIN,
            kelvin=bridge,
            source_current=source_current,
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
