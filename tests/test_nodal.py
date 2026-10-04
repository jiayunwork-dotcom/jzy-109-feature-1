"""通用节点求解器判据：手算网络、零欧短接、戴维南内阻、奇异与病态。"""
import pytest

from app.bridge import nodal


def test_two_resistor_divider_hand_computable():
    """手算基准：1 kΩ 与 3 kΩ 分压，5 V 源 → 中点 3.75 V。"""
    network = nodal.ResistiveNetwork(
        resistors=(("a", "m", 1000.0), ("m", "g", 3000.0)),
        fixed_voltages={"a": 5.0, "g": 0.0},
    )
    solution = nodal.solve(network)
    assert solution.voltage("m") == pytest.approx(3.75, rel=1e-12)


def test_current_source_injection():
    """1 mA 注入 2 kΩ 单电阻 → 端电压 2 V。"""
    network = nodal.ResistiveNetwork(
        resistors=(("p", "g", 2000.0),),
        current_sources=(("p", "g", 0.001),),
        fixed_voltages={"g": 0.0},
    )
    solution = nodal.solve(network)
    assert solution.voltage("p") == pytest.approx(2.0, rel=1e-12)


def test_zero_ohm_merges_nodes():
    """零欧短接的两节点电位相同，且不需要写 1/0 电导。"""
    network = nodal.ResistiveNetwork(
        resistors=(("a", "x", 100.0), ("x", "y", 0.0), ("y", "g", 300.0)),
        fixed_voltages={"a": 4.0, "g": 0.0},
    )
    solution = nodal.solve(network)
    assert solution.voltage("x") == pytest.approx(solution.voltage("y"), abs=1e-15)
    assert solution.voltage("x") == pytest.approx(3.0, rel=1e-12)


def test_equivalent_resistance_series_parallel():
    """手算：两 100 Ω 并联为 50 Ω，再串 10 Ω 为 60 Ω。"""
    resistors = (
        ("p", "m1", 100.0),
        ("p", "m2", 100.0),
        ("m1", "n", 0.0),
        ("m2", "n", 0.0),
        ("n", "q", 10.0),
    )
    assert nodal.equivalent_resistance(resistors, "p", "q") == pytest.approx(60.0, rel=1e-12)


def test_equivalent_resistance_short_is_zero():
    """端口被零欧路径短接时等效内阻为 0。"""
    resistors = (("p", "x", 5.0), ("x", "q", 7.0), ("p", "q", 0.0))
    assert nodal.equivalent_resistance(resistors, "p", "q") == 0.0


def test_singular_isolated_node_group():
    """与参考点无任何电导连接的孤立节点组 → 带原因的结构奇异错误。"""
    network = nodal.ResistiveNetwork(
        resistors=(("g", "a", 1.0), ("x", "y", 1.0)),
        fixed_voltages={"g": 0.0},
    )
    with pytest.raises(nodal.NetworkError) as exc:
        nodal.solve(network)
    assert exc.value.code == "circuit_singular"
    assert "孤立" in exc.value.message


def test_singular_fixed_voltage_conflict():
    """零欧短接把两个不同电位的固定点连成同一点 → 结构奇异。"""
    network = nodal.ResistiveNetwork(
        resistors=(("a", "b", 0.0),),
        fixed_voltages={"a": 1.0, "b": 2.0},
    )
    with pytest.raises(nodal.NetworkError) as exc:
        nodal.solve(network)
    assert exc.value.code == "circuit_singular"


def test_singular_floating_network_without_ground():
    """没有任何固定电位点的纯电阻网络无法定电位 → 结构奇异。"""
    network = nodal.ResistiveNetwork(resistors=(("a", "b", 1.0),))
    with pytest.raises(nodal.NetworkError) as exc:
        nodal.solve(network)
    assert exc.value.code == "circuit_singular"


def test_ill_conditioned_near_floating_node():
    """节点 b 只经两只超大电阻（1e13 Ω，相对电导 1e-13）弱耦合到网络。

    它有直流通路、矩阵非奇异，但实测条件数约 5e12（超过 COND_LIMIT），
    节点电位的有效数字不足以支撑毫欧级标定 → 判病态，错误带回实测
    主元比与阈值，且不把任何线性代数异常/NaN/Inf 透出给调用方。

    物理对应：某取压节点几乎只接触不上（虚接），仍有漏电通路但结果不可信。
    """
    r_weak = 1.0e13
    network = nodal.ResistiveNetwork(
        resistors=(("s", "a", 1.0), ("a", "b", r_weak), ("b", "g", r_weak)),
        fixed_voltages={"s": 1.0, "g": 0.0},
    )
    with pytest.raises(nodal.NetworkError) as exc:
        nodal.solve(network)
    assert exc.value.code == "circuit_ill_conditioned"
    assert exc.value.details["pivot_ratio"] > nodal.COND_LIMIT
    assert exc.value.details["cond_limit"] == nodal.COND_LIMIT
    assert "病态" in exc.value.message


def test_borderline_weak_tie_above_ill_threshold_still_solves():
    """弱连接但条件数在阈值内（相对电导 1e-11）的网络仍可正常求解。"""
    r_weak = 1.0e11
    network = nodal.ResistiveNetwork(
        resistors=(("s", "a", 1.0), ("a", "b", r_weak), ("b", "g", r_weak)),
        fixed_voltages={"s": 1.0, "g": 0.0},
    )
    solution = nodal.solve(network)
    # 对称弱耦合：b 电位是 s 与 g 的中点
    assert solution.voltage("b") == pytest.approx(0.5, rel=1e-9)


def test_non_finite_result_is_caught_not_leaked():
    """解中若出现非数/无穷大，翻译为带原因错误而不是直接透出。"""
    # 构造一个近奇异 2 节点系统（极大注入 + 极小电导仍有限时不应触发；
    # 这里通过负电阻这种非法构造确认错误通道不泄露原始异常类型）
    network = nodal.ResistiveNetwork(
        resistors=(("a", "b", -1.0),), fixed_voltages={"a": 1.0}
    )
    with pytest.raises(nodal.NetworkError):
        nodal.solve(network)
