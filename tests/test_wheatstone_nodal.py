"""四臂惠斯通电桥：通用节点方程底子与既有闭式逐项一致性锁定。

闭式（forward/thevenin）保留为对照；两条路径相对误差不得超过 1e-9。
"""
import random

import pytest

from app.bridge import forward, thevenin, wheatstone_nodal
from app.bridge.topology import ArmSet

REL_TOL = 1e-9


def test_hand_computable_case_matches():
    """可手算例：R1=100,R2=200,R3=300,R4=100,Vs=12 → V_B=9,V_D=4,Vout=5。"""
    arms = ArmSet(100.0, 200.0, 300.0, 100.0)
    result = wheatstone_nodal.analyze(arms, 12.0)
    assert result.node_voltages_open["B"] == pytest.approx(9.0)
    assert result.node_voltages_open["D"] == pytest.approx(4.0)
    assert result.open_circuit_voltage == pytest.approx(5.0)
    assert forward.open_circuit_output(arms, 12.0) == pytest.approx(
        result.open_circuit_voltage, rel=REL_TOL
    )


def test_balanced_zero_on_both_paths():
    arms = ArmSet(100.0, 200.0, 300.0, 600.0)
    assert wheatstone_nodal.nodal_open_circuit_output(arms, 12.0) == pytest.approx(
        0.0, abs=1e-14
    )


def test_thevenin_resistance_matches_closed_form():
    arms = ArmSet(1000.0, 1000.0, 1000.0, 1000.0)
    result = wheatstone_nodal.analyze(arms, 10.0)
    assert result.thevenin_resistance == pytest.approx(
        thevenin.thevenin_resistance(arms), rel=REL_TOL
    )
    assert result.thevenin_resistance == pytest.approx(1000.0)


@pytest.mark.parametrize("rg", [1.0, 47.0, 150.0, 1000.0, 1e6])
def test_galvanometer_current_matches_closed_form(rg):
    arms = ArmSet(100.0, 200.0, 300.0, 500.0)
    for vs in (-12.0, -3.0, 0.5, 12.0):
        nodal = wheatstone_nodal.nodal_galvanometer_current(arms, vs, rg)
        closed = thevenin.galvanometer_current(arms, vs, rg)
        if closed == 0.0:
            assert nodal == pytest.approx(0.0, abs=1e-15)
        else:
            assert nodal == pytest.approx(closed, rel=REL_TOL)


def test_zero_source_both_paths_zero():
    arms = ArmSet(100.0, 200.0, 300.0, 500.0)
    result = wheatstone_nodal.analyze(arms, 0.0, 50.0)
    assert result.open_circuit_voltage == 0.0
    assert result.loaded_current == 0.0


def test_wide_random_sweep_locks_paths():
    """随机扫六十年动态范围的臂阻与桥源，两路径最坏相对误差锁在 1e-9 内。"""
    rng = random.Random(20261004)
    worst = 0.0
    for _ in range(300):
        arms = ArmSet(*[10 ** rng.uniform(-6, 6) for _ in range(4)])
        vs = rng.choice([-1.0, 1.0]) * 10 ** rng.uniform(-2, 2)
        rg = 10 ** rng.uniform(-3, 6)

        result = wheatstone_nodal.analyze(arms, vs, rg)
        ref_v = forward.open_circuit_output(arms, vs)
        worst = max(worst, abs(result.open_circuit_voltage - ref_v) / max(abs(ref_v), 1e-300))

        ref_i = thevenin.galvanometer_current(arms, vs, rg)
        if ref_i != 0.0:
            worst = max(worst, abs(result.loaded_current - ref_i) / abs(ref_i))
    assert worst <= REL_TOL
