"""四臂惠斯通电桥 → 通用电阻网络的拓扑适配。

节点命名沿用 :mod:`app.bridge.topology` 的编号约定：

    A（桥源正端）—R1— B —R3— C（桥源负端，参考地）
                   └ G（检流计，可选）┘
    A —R2— D —R4— C

正算时 A 钳位到桥源电压、C 钳位到地；独立源置零的无源网里 A、C 同为
地电位（电压源短路），故被动工厂仍把 C 接地。
"""
from __future__ import annotations

from typing import Callable

from app.bridge.topology import ArmSet
from app.circuit.network import Network

NODE_A = "A"
NODE_B = "B"
NODE_C = "C"
NODE_D = "D"

#: 检流计输出端子（正方向 B → D）
PLUS_TERMINAL = NODE_B
MINUS_TERMINAL = NODE_D
GROUND = NODE_C


def network_factory(arms: ArmSet, source_voltage: float) -> Callable[[], Network]:
    """带桥源的网络工厂：A 钳位 Vs，C 接地。"""

    def factory() -> Network:
        net = Network()
        net.resistor(NODE_A, NODE_B, arms.r1)
        net.resistor(NODE_A, NODE_D, arms.r2)
        net.resistor(NODE_B, NODE_C, arms.r3)
        net.resistor(NODE_D, NODE_C, arms.r4)
        net.fix_voltage(NODE_A, source_voltage)
        net.fix_voltage(NODE_C, 0.0)
        return net

    return factory


def passive_factory(arms: ArmSet) -> Callable[[], Network]:
    """独立源置零（A 与 C 短接为地）的无源网络工厂。"""

    def factory() -> Network:
        net = Network()
        net.resistor(NODE_A, NODE_B, arms.r1)
        net.resistor(NODE_A, NODE_D, arms.r2)
        net.resistor(NODE_B, NODE_C, arms.r3)
        net.resistor(NODE_D, NODE_C, arms.r4)
        # 电压源短路：A 与 C 同电位（地）
        net.fix_voltage(NODE_C, 0.0)
        net.short(NODE_A, NODE_C)
        return net

    return factory
