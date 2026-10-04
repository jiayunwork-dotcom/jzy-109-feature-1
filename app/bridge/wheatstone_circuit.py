"""四臂惠斯通电桥 → 通用电阻网络。

把 topology 中的四臂拓扑按节点编号翻译成 :mod:`app.bridge.nodal` 的
网络描述，使四臂电桥的正算（开路输出、戴维南等效、检流计电流）
与开尔文双电桥走同一套节点方程求解底子，而不是各抄一份专用公式。

节点编号沿用 topology 的拓扑图：

            A (桥源正端，钳位 Vs)
           / \\
         R1     R2
         /       \\
        B ───G─── D      B、D：输出端子；G：检流计（可选接入）
         \\       /
         R3     R4
           \\   /
            C (桥源负端，参考地 0 V)

闭式结果（forward/thevenin 模块）保留为对照路径，测试锁住两条路径
逐项吻合（相对误差不超过 1e-9）。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.bridge import nodal
from app.bridge.topology import ArmSet

#: 节点名
A, B, C, D = "A", "B", "C", "D"


@dataclass(frozen=True)
class WheatstoneAnalysis:
    """正算结果：开路输出、戴维南等效量，以及（若接检流计）偏转电流。"""

    v_b: float
    v_d: float
    open_circuit_voltage: float
    thevenin_resistance: float
    galvanometer_current: float | None
    galvanometer_voltage: float | None


def _passive_resistors(arms: ArmSet) -> tuple[tuple[str, str, float], ...]:
    return (
        (A, B, arms.r1),
        (A, D, arms.r2),
        (B, C, arms.r3),
        (D, C, arms.r4),
    )


def thevenin_resistance(arms: ArmSet) -> float:
    """从 B、D 看进去的等效内阻：理想电压源置零即把 A、C 短接为同地。"""
    return nodal.equivalent_resistance(
        _passive_resistors(arms), B, D, grounded_nodes=(A, C)
    )


def analyze(
    arms: ArmSet,
    source_voltage: float,
    galvanometer_resistance: float | None = None,
) -> WheatstoneAnalysis:
    """正算：开路输出、戴维南内阻，以及接入检流计后的偏转电流。

    全部量值都由通用节点方程解出；``galvanometer_resistance=None`` 时
    只算开路量。
    """
    resistors = list(_passive_resistors(arms))
    if galvanometer_resistance is not None:
        resistors.append((B, D, galvanometer_resistance))
    network = nodal.ResistiveNetwork(
        resistors=tuple(resistors),
        fixed_voltages={A: source_voltage, C: 0.0},
    )
    solution = nodal.solve(network)
    v_b = solution.voltage(B)
    v_d = solution.voltage(D)

    current = voltage = None
    if galvanometer_resistance is not None:
        current = (v_b - v_d) / galvanometer_resistance
        voltage = v_b - v_d

    return WheatstoneAnalysis(
        v_b=v_b,
        v_d=v_d,
        open_circuit_voltage=v_b - v_d,
        thevenin_resistance=thevenin_resistance(arms),
        galvanometer_current=current,
        galvanometer_voltage=voltage,
    )
