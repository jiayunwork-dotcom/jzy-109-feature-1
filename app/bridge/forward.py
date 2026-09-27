"""开路输出电压（正算）：两条分压支路的电位差。

以 C 为参考地、A 接桥源正端：
  V_B = Vs · R3/(R1+R3)   （左支路 A→R1→B→R3→C 的分压）
  V_D = Vs · R4/(R2+R4)   （右支路 A→R2→D→R4→C 的分压）
  V_out = V_B − V_D = Vs · ( R3/(R1+R3) − R4/(R2+R4) )

桥源电压为零时输出自然为零，属正常情形，由上层标明即可。
"""
from __future__ import annotations

from app.bridge.topology import ArmSet


def divider_voltage_b(arms: ArmSet, source_voltage: float) -> float:
    """左支路输出端 B 的对地电位。"""
    return source_voltage * arms.r3 / (arms.r1 + arms.r3)


def divider_voltage_d(arms: ArmSet, source_voltage: float) -> float:
    """右支路输出端 D 的对地电位。"""
    return source_voltage * arms.r4 / (arms.r2 + arms.r4)


def open_circuit_output(arms: ArmSet, source_voltage: float) -> float:
    """开路（未接检流计）输出电压 V_out = V_B − V_D。"""
    return divider_voltage_b(arms, source_voltage) - divider_voltage_d(arms, source_voltage)
