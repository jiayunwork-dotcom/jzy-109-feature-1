"""戴维南分析：开路电压、等效内阻、带载电流，全部由节点方程给出。

给定网络的构造方式与两个输出端子名，本模块提供两种激励下的统一求解：

1. **带源工况**（``factory`` 原样搭网）：解得开路/带载时的全节点电位；
2. **置零工况**（``passive_factory`` 搭无源网，独立源置零）：在两个输出
   端子间注入单位电流，端子电位差即戴维南等效内阻 R_th——置零后的
   网络里没有任何钳位节点时，自动把 ``ground`` 作为参考地补进网络。

开路电压 V_th、检流计电流 I_g 因此出自同一套节点方程，四臂电桥与双电桥
都只负责描述自己的拓扑，不各写一套电路公式：

* ``V_th`` 由带源开路网络的节点解得到；
* ``R_th`` 由独立源置零后在输出端注入单位电流的节点解（端子电位差）得到；
* ``I_g = V_th/(R_th + R_g)``。带载网络的节点解照算（用于节点电位/交叉
  核对），但电流**不**由带载端电压除以（可能很小的）R_g 反推——R_g ≪ R_th
  时端电压是两个相近大数之差，除小电阻会把舍入误差放大成巨大相对误差；
  用两个节点解直接得到的 V_th、R_th 组合求电流在全量程都稳。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.circuit.network import Network
from app.circuit.solver import node_voltages

NetworkFactory = Callable[[], Network]


@dataclass(frozen=True)
class TheveninResult:
    open_circuit_voltage: float
    thevenin_resistance: float
    loaded_current: float | None
    loaded_voltage: float | None
    node_voltages_open: dict[str, float]
    node_voltages_loaded: dict[str, float] | None


def _solve(factory: NetworkFactory) -> dict[str, float]:
    return node_voltages(factory())


def thevenin_analysis(
    factory: NetworkFactory,
    passive_factory: NetworkFactory,
    plus_terminal: str,
    minus_terminal: str,
    ground: str,
    galvanometer_resistance: float | None = None,
) -> TheveninResult:
    """开路输出、戴维南等效、检流计偏转（可选）一次给出。

    ``loaded_current`` 正方向为 plus_terminal → 检流计 → minus_terminal。
    """
    v_open = _solve(factory)
    v_th = v_open[plus_terminal] - v_open[minus_terminal]

    def passive_with_probe() -> Network:
        net = passive_factory()
        net.node(ground)
        # 无源网若没有任何电位钳位点，节点电位只能确定到一个常数：
        # 补一个参考地（该节点原本就是物理参考点，如桥源负端/恒流源端）。
        if not net.has_fixed_voltage:
            net.fix_voltage(ground, 0.0)
        net.inject(plus_terminal, 1.0)
        net.inject(minus_terminal, -1.0)
        return net

    v_passive = _solve(passive_with_probe)
    r_th = v_passive[plus_terminal] - v_passive[minus_terminal]

    v_loaded = None
    i_g = None
    v_g = None
    if galvanometer_resistance is not None:
        # 检流计电流直接由戴维南关系算，不从带载端电压除以（可能很小的）R_g
        # 反推——后者在 R_g ≪ R_th 时会把端电压的舍入误差放大成大的相对误差。
        # I_g = V_th/(R_th+R_g) 只用开路电压与等效内阻两个量，数值上稳。
        i_g = v_th / (r_th + galvanometer_resistance)

        def loaded_factory() -> Network:
            net = factory()
            net.resistor(plus_terminal, minus_terminal, galvanometer_resistance)
            return net

        v_loaded = _solve(loaded_factory)
        v_g = i_g * galvanometer_resistance

    return TheveninResult(
        open_circuit_voltage=v_th,
        thevenin_resistance=r_th,
        loaded_current=i_g,
        loaded_voltage=v_g,
        node_voltages_open=v_open,
        node_voltages_loaded=v_loaded,
    )
