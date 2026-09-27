"""接入检流计后的戴维南等效求解。

从输出端子 B、D 看进去（桥源置零后求等效内阻）：
  V_th = 开路输出电压（见 forward 模块）
  R_th = (R1‖R3) + (R2‖R4) = R1·R3/(R1+R3) + R2·R4/(R2+R4)

接入内阻 R_g 的检流计后，严格按分压/欧姆定律求解：
  I_g = V_th / (R_th + R_g)     —— 检流计偏转量与 I_g 成正比
  V_g = I_g · R_g               —— 检流计两端实际电压
"""
from __future__ import annotations

from app.bridge import forward
from app.bridge.topology import ArmSet


def thevenin_voltage(arms: ArmSet, source_voltage: float) -> float:
    """戴维南等效电压，即 B、D 间开路电压。"""
    return forward.open_circuit_output(arms, source_voltage)


def thevenin_resistance(arms: ArmSet) -> float:
    """戴维南等效内阻：(R1‖R3) + (R2‖R4)。"""
    left = arms.r1 * arms.r3 / (arms.r1 + arms.r3)
    right = arms.r2 * arms.r4 / (arms.r2 + arms.r4)
    return left + right


def galvanometer_current(
    arms: ArmSet, source_voltage: float, galvanometer_resistance: float
) -> float:
    """检流计电流 I_g = V_th / (R_th + R_g)，偏转量与之成正比。"""
    v_th = thevenin_voltage(arms, source_voltage)
    return v_th / (thevenin_resistance(arms) + galvanometer_resistance)


def galvanometer_voltage(
    arms: ArmSet, source_voltage: float, galvanometer_resistance: float
) -> float:
    """检流计两端实际电压 V_g = I_g · R_g。"""
    return galvanometer_current(arms, source_voltage, galvanometer_resistance) * galvanometer_resistance
