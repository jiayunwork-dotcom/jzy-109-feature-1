"""开尔文双电桥正算：开路输出、戴维南等效、检流计偏转——全部来自节点方程。

不使用反推侧的闭式解；把整张电路（含 8 个端钮接触电阻）翻译成
:mod:`app.bridge.nodal` 的通用电阻网络后求解。与四臂电桥共用同一套
求解底子。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.bridge import nodal
from app.bridge.kelvin_topology import (
    GROUND,
    P1,
    P2,
    KelvinConfig,
    build_network,
    passive_resistors,
)


@dataclass(frozen=True)
class KelvinAnalysis:
    """双电桥正算结果。"""

    v_p1: float = 0.0
    v_p2: float = 0.0
    open_circuit_voltage: float = 0.0
    thevenin_resistance: float | None = None
    galvanometer_current: float | None = None
    galvanometer_voltage: float | None = None
    source_current: float = 0.0


def open_circuit_voltage(config: KelvinConfig, rx: float, source_current: float) -> float:
    """检流计端口 P1−P2 的开路输出电压（伏）。"""
    network = build_network(config, rx, source_current)
    voltage, _ = nodal.port_voltage(network, P1, P2)
    return voltage


def thevenin_resistance(config: KelvinConfig, rx: float) -> float:
    """从 P1、P2 看进去的戴维南等效内阻（恒流源置零即开路，地保留为参考）。"""
    return nodal.equivalent_resistance(
        passive_resistors(config, rx), P1, P2, grounded_nodes=(GROUND,)
    )


def analyze(
    config: KelvinConfig,
    rx: float,
    source_current: float,
    galvanometer_resistance: float | None = None,
) -> KelvinAnalysis:
    """正算：开路输出 + （可选）接入检流计后的实际偏转电流。"""
    network = build_network(config, rx, source_current, galvanometer_resistance)
    solution = nodal.solve(network)
    v_p1 = solution.voltage(P1)
    v_p2 = solution.voltage(P2)
    v_open = v_p1 - v_p2

    current = voltage = None
    if galvanometer_resistance is not None:
        current = (v_p1 - v_p2) / galvanometer_resistance
        voltage = v_p1 - v_p2

    return KelvinAnalysis(
        v_p1=v_p1,
        v_p2=v_p2,
        open_circuit_voltage=v_open,
        thevenin_resistance=thevenin_resistance(config, rx),
        galvanometer_current=current,
        galvanometer_voltage=voltage,
        source_current=source_current,
    )
