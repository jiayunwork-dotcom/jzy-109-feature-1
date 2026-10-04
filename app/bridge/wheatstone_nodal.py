"""四臂惠斯通电桥的节点方程正算（通用电路求解层的四臂适配）。

与 :mod:`app.bridge.forward` / :mod:`app.bridge.thevenin` 的闭式结果并存：
闭式仍为接口返回值与对照基准，本模块走整张电路的节点方程，自动化测试把
两条路径逐项锁死（相对误差不超过 1e-9）。
"""
from __future__ import annotations

from app.bridge import wheatstone_network
from app.bridge.topology import ArmSet
from app.circuit.analysis import TheveninResult, thevenin_analysis


def analyze(arms: ArmSet, source_voltage: float,
            galvanometer_resistance: float | None = None) -> TheveninResult:
    """四臂电桥：开路输出、戴维南等效、检流计电流（全部由节点方程给出）。"""
    return thevenin_analysis(
        wheatstone_network.network_factory(arms, source_voltage),
        wheatstone_network.passive_factory(arms),
        wheatstone_network.PLUS_TERMINAL,
        wheatstone_network.MINUS_TERMINAL,
        wheatstone_network.GROUND,
        galvanometer_resistance,
    )


def nodal_open_circuit_output(arms: ArmSet, source_voltage: float) -> float:
    """节点方程给出的开路输出 V_B − V_D。"""
    return analyze(arms, source_voltage).open_circuit_voltage


def nodal_galvanometer_current(
    arms: ArmSet, source_voltage: float, galvanometer_resistance: float
) -> float:
    """节点方程给出的检流计电流。"""
    result = analyze(arms, source_voltage, galvanometer_resistance)
    assert result.loaded_current is not None
    return result.loaded_current
