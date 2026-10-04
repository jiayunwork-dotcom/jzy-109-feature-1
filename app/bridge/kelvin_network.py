"""开尔文双电桥 → 通用电阻网络的拓扑适配。

全部 8 个接触电阻都作为真实元件进网（编号约定见
:mod:`app.bridge.kelvin_topology`），轭线/接触取零时用零电阻收缩，绝不在
结果上事后加减：

主回路（恒流源驱动）::

    S+ ─rc1─ n1 ─R_x─ n2 ─rc2─ y2 ─[轭线 yoke]─ y3 ─rc3─ n3 ─R_s─ n4 ─rc4─ S-

比例臂（电位端接触串在臂内，p1..p4 是真正的电位取点）::

    n1 ─rp1─ p1 ─R1─ M ─R2─ p3 ─rp3─ n4   （外臂在 M 汇合）
    n2 ─rp2─ p2 ─R3─ N ─R4─ p4 ─rp4─ n3   （内臂在 N 汇合）
    M ───────────── R_g（可选）────────── N

外臂支路与整条主回路（R_x+轭线+R_s）并联，内臂支路与轭线段并联；
恒流源：S+ 注入 I_s、S- 抽出 I_s，S- 取参考地。
"""
from __future__ import annotations

from typing import Callable

from app.bridge.kelvin_topology import KelvinBridge
from app.circuit.network import Network

#: 输出端子（检流计正方向 M → N）与参考地
PLUS_TERMINAL = "M"
MINUS_TERMINAL = "N"
GROUND = "S-"

#: 主回路内部节点
N1, N2, N3, N4 = "n1", "n2", "n3", "n4"
Y2, Y3 = "y2", "y3"  # 轭线两侧（rc2、rc3 的内端）
S_PLUS = "S+"


def _segment(net: Network, a: str, b: str, resistance: float) -> None:
    """a—b 间接一只电阻；阻值为零时收缩成同一节点。"""
    if resistance == 0.0:
        net.short(a, b)
    else:
        net.resistor(a, b, resistance)


def _ratio_arm(net: Network, end: str, sense: str, junction: str,
               contact: float, arm: float) -> None:
    """end ─rc(电位端)─ sense ─比例臂─ junction；接触为零时收缩。"""
    net.node(sense)
    _segment(net, end, sense, contact)
    net.resistor(sense, junction, arm)  # 比例臂本身必须为正，由校验保证


def network_factory(bridge: KelvinBridge, source_current: float) -> Callable[[], Network]:
    """带恒流源的双电桥网络工厂。"""

    def factory() -> Network:
        net = Network()

        # ---- 主回路 ----
        _segment(net, S_PLUS, N1, bridge.rc1)
        net.resistor(N1, N2, bridge.rx)
        net.node(Y2)
        _segment(net, N2, Y2, bridge.rc2)
        _segment(net, Y2, Y3, bridge.yoke)
        net.node(N3)
        _segment(net, Y3, N3, bridge.rc3)
        net.resistor(N3, N4, bridge.rs)
        _segment(net, N4, GROUND, bridge.rc4)

        # ---- 比例臂（含电位端接触）；外臂汇合于 M，内臂汇合于 N ----
        net.node(PLUS_TERMINAL)
        net.node(MINUS_TERMINAL)
        _ratio_arm(net, N1, "p1", PLUS_TERMINAL, bridge.rp1, bridge.r1)
        _ratio_arm(net, N4, "p3", PLUS_TERMINAL, bridge.rp3, bridge.r2)
        _ratio_arm(net, N2, "p2", MINUS_TERMINAL, bridge.rp2, bridge.r3)
        _ratio_arm(net, N3, "p4", MINUS_TERMINAL, bridge.rp4, bridge.r4)

        # ---- 恒流源 ----
        net.fix_voltage(GROUND, 0.0)
        net.inject(S_PLUS, source_current)
        net.inject(GROUND, -source_current)
        return net

    return factory


def passive_factory(bridge: KelvinBridge) -> Callable[[], Network]:
    """独立源置零的无源网：恒流源开路（撤注入），S- 留作参考地。"""

    def factory() -> Network:
        # 以零电流搭出完整拓扑（注入均为 0），再撤注入即源开路。
        net = network_factory(bridge, 0.0)()
        net._inject.clear()  # noqa: SLF001 - 工厂自有网络，恒流源置零即开路
        return net

    return factory
