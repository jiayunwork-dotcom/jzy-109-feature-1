"""通用电阻网络节点求解：基本求解、零电阻收缩、奇异与病态判定。

病态/奇异的方案选择（选主元消元 + 平衡标度 + 条件数估计）见
app/circuit/solver.py 与 README「奇异与病态判定」。
"""
import math

import pytest

from app.circuit.network import Network
from app.circuit.solver import (
    CONDITION_LIMIT,
    NetworkEquationError,
    gaussian_solve,
    node_voltages,
)


def test_simple_divider():
    """手算：10 Ω 与 10 Ω 串联接 10 V，中点 5 V。"""
    net = Network()
    net.resistor("A", "M", 10.0)
    net.resistor("M", "C", 10.0)
    net.fix_voltage("A", 10.0)
    net.fix_voltage("C", 0.0)
    v = node_voltages(net)
    assert v["M"] == pytest.approx(5.0)


def test_current_source_and_injection():
    """恒流源 1 A 注入 5 Ω 到地：节点电位 5 V。"""
    net = Network()
    net.resistor("x", "g", 5.0)
    net.fix_voltage("g", 0.0)
    net.inject("x", 1.0)
    assert node_voltages(net)["x"] == pytest.approx(5.0)


def test_zero_resistance_shorts_nodes():
    """零电阻把两端收缩成等电位，而不是塞 1/0 的无穷电导。"""
    net = Network()
    net.resistor("A", "x", 10.0)
    net.short("x", "y")
    net.resistor("y", "C", 10.0)
    net.fix_voltage("A", 10.0)
    net.fix_voltage("C", 0.0)
    v = node_voltages(net)
    assert v["x"] == pytest.approx(5.0)
    assert v["y"] == v["x"]


def test_finite_results_no_inf_nan():
    net = Network()
    net.resistor("a", "b", 2.0)
    net.resistor("b", "c", 3.0)
    net.fix_voltage("a", 4.0)
    net.fix_voltage("c", 0.0)
    v = node_voltages(net)
    for value in v.values():
        assert math.isfinite(value)


def test_singular_floating_node_detected():
    """悬空节点（自由节点没有任何电导到地）判奇异，不抛 ZeroDivisionError。"""
    net = Network()
    net.resistor("a", "b", 1.0)
    net.fix_voltage("a", 1.0)
    net.node("f")
    net.resistor("f", "g", 2.0)  # f、g 构成与参考点无关的孤立自由分量
    with pytest.raises(NetworkEquationError) as exc:
        node_voltages(net)
    assert exc.value.code == "network_singular"
    assert "奇异" in exc.value.message


def test_singular_conflicting_voltage_clamps():
    """被零电阻短接的两端被钳到不同电位（理想电压源短接）判奇异。"""
    net = Network()
    net.short("x", "y")
    net.fix_voltage("x", 1.0)
    net.fix_voltage("y", 2.0)
    with pytest.raises(NetworkEquationError) as exc:
        node_voltages(net)
    assert exc.value.code == "network_singular"


def test_ill_conditioned_floating_cluster():
    """两节点强耦合（1 Ω）却各只经超大电阻（1e14 Ω）接地：浮簇近奇异。

    标度后条件数随弱接地比线性增长（约 2e14），越过 1e12 上限判病态。
    """
    net = Network()
    net.resistor("c", "d", 1.0)
    net.resistor("c", "g", 1e14)
    net.resistor("d", "g", 1e14)
    net.fix_voltage("g", 0.0)
    net.inject("c", 1.0)
    net.inject("d", -1.0)
    with pytest.raises(NetworkEquationError) as exc:
        node_voltages(net)
    assert exc.value.code == "network_ill_conditioned"
    assert "条件数" in exc.value.message


def test_well_conditioned_large_but_uniform_spread_ok():
    """所有臂同比放大（如整体 1e6 倍）不改变网络条件数，不应误判病态。"""
    net = Network()
    net.resistor("a", "b", 1e6)
    net.resistor("b", "c", 1e6)
    net.resistor("a", "c", 2e6)
    net.fix_voltage("a", 1.0)
    net.fix_voltage("c", 0.0)
    v = node_voltages(net)
    assert math.isfinite(v["b"])


def test_condition_limit_constant():
    assert CONDITION_LIMIT == 1e12


def test_empty_system():
    """无自由节点（全网固定电位）时返回空解，不报错。"""
    net = Network()
    net.fix_voltage("a", 1.0)
    assert node_voltages(net) == {"a": 1.0}
