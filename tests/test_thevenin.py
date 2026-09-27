"""戴维南等效判据：与直接节点分析交叉核对、开路极限、平衡零电流。"""
import pytest

from app.bridge import forward, thevenin
from app.bridge.topology import ArmSet

BENCH = ArmSet(r1=1000.0, r2=1000.0, r3=1000.0, r4=1000.0)


def _nodal_galvanometer_current(arms: ArmSet, vs: float, rg: float) -> float:
    """独立参照：对 B、D 两节点直接列 KCL 解 2×2 线性方程组。"""
    a11 = 1.0 / arms.r1 + 1.0 / arms.r3 + 1.0 / rg
    a22 = 1.0 / arms.r2 + 1.0 / arms.r4 + 1.0 / rg
    a12 = a21 = -1.0 / rg
    b1 = vs / arms.r1
    b2 = vs / arms.r2
    det = a11 * a22 - a12 * a21
    v_b = (b1 * a22 - a12 * b2) / det
    v_d = (a11 * b2 - a21 * b1) / det
    return (v_b - v_d) / rg


def test_thevenin_resistance_all_equal():
    """手算基准：1000‖1000 = 500，两条支路串联得 1000 Ω。"""
    assert thevenin.thevenin_resistance(BENCH) == 1000.0


def test_galvanometer_current_matches_direct_nodal_analysis():
    """戴维南结果必须与直接节点分析一致（不是口头估算）。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=500.0)
    for vs, rg in ((10.0, 150.0), (5.0, 47.0), (12.0, 1000.0)):
        expected = _nodal_galvanometer_current(arms, vs, rg)
        assert thevenin.galvanometer_current(arms, vs, rg) == pytest.approx(
            expected, rel=1e-12
        )


def test_open_circuit_limit_for_large_galvanometer_resistance():
    """R_g 趋于无穷时，检流计端电压趋于开路输出。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=500.0)
    v_oc = forward.open_circuit_output(arms, 10.0)
    v_g = thevenin.galvanometer_voltage(arms, 10.0, 1e12)
    assert v_g == pytest.approx(v_oc, rel=1e-6)


def test_balanced_bridge_zero_galvanometer_current():
    """平衡时检流计电流为零。"""
    assert thevenin.galvanometer_current(BENCH, 10.0, 50.0) == 0.0


def test_galvanometer_current_scales_with_source():
    """同一负载下，桥源翻倍则检流计电流翻倍。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=500.0)
    i1 = thevenin.galvanometer_current(arms, 6.0, 150.0)
    i2 = thevenin.galvanometer_current(arms, 12.0, 150.0)
    assert abs(i2) == pytest.approx(2.0 * abs(i1), rel=1e-15)
