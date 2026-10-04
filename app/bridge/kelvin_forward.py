"""开尔文双电桥正算：开路输出、戴维南等效、检流计偏转。

双电桥正算**不用闭式解**，而是解整张电路（含全部接触电阻元件）的节点
方程，统一走 :mod:`app.circuit.analysis`——与四臂电桥正算共用同一底子。
反解的闭式见 :mod:`app.bridge.kelvin_balance`。
"""
from __future__ import annotations

from app.bridge import kelvin_network
from app.bridge.kelvin_topology import KelvinBridge
from app.circuit.analysis import TheveninResult, thevenin_analysis


def analyze(bridge: KelvinBridge, source_current: float,
            galvanometer_resistance: float | None = None) -> TheveninResult:
    """双电桥：开路输出 V_M−V_N、R_th、检流计电流（全部由节点方程给出）。"""
    return thevenin_analysis(
        kelvin_network.network_factory(bridge, source_current),
        kelvin_network.passive_factory(bridge),
        kelvin_network.PLUS_TERMINAL,
        kelvin_network.MINUS_TERMINAL,
        kelvin_network.GROUND,
        galvanometer_resistance,
    )


def open_circuit_output(bridge: KelvinBridge, source_current: float) -> float:
    """开路（未接检流计）输出电压 V_M − V_N（伏）。"""
    return analyze(bridge, source_current).open_circuit_voltage


def galvanometer_current(
    bridge: KelvinBridge, source_current: float, galvanometer_resistance: float
) -> float:
    """接内阻 R_g 的检流计后，正方向 M→N 的偏转电流（安）。"""
    result = analyze(bridge, source_current, galvanometer_resistance)
    assert result.loaded_current is not None
    return result.loaded_current
