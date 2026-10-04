"""四臂电桥：通用节点方程路径与历史闭式结果逐项一致（容差 1e-9）。

闭式路径（forward/thevenin）保留为对外结果；本测试把两条路径锁死，
任何后续改动让它们分家都会在这里失败。
"""
import itertools

import pytest

from app.bridge import forward, thevenin, wheatstone_circuit
from app.bridge.topology import ArmSet

ARMS_SETS = [
    ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=500.0),
    ArmSet(r1=1000.0, r2=1000.0, r3=1000.0, r4=1000.0),
    ArmSet(r1=120.0, r2=350.0, r3=780.0, r4=2275.0),
    ArmSet(r1=47.5, r2=1230.0, r3=86.4, r4=0.33),
    ArmSet(r1=2.2, r2=4.4e4, r3=0.75, r4=91.0),
]
SOURCE_VOLTAGES = [12.0, 5.0, -3.3, 0.0]
GALVANOMETERS = [None, 50.0, 150.0, 1000.0]


@pytest.mark.parametrize("arms", ARMS_SETS)
@pytest.mark.parametrize("vs", SOURCE_VOLTAGES)
def test_open_circuit_outputs_match(arms, vs):
    """节点方程的 B/D 电位与开路输出逐项等于闭式分压结果。"""
    result = wheatstone_circuit.analyze(arms, vs)
    assert result.v_b == pytest.approx(forward.divider_voltage_b(arms, vs), rel=1e-9)
    assert result.v_d == pytest.approx(forward.divider_voltage_d(arms, vs), rel=1e-9)
    assert result.open_circuit_voltage == pytest.approx(
        forward.open_circuit_output(arms, vs), rel=1e-9, abs=1e-12
    )


@pytest.mark.parametrize("arms", ARMS_SETS)
def test_thevenin_resistance_matches(arms):
    assert wheatstone_circuit.thevenin_resistance(arms) == pytest.approx(
        thevenin.thevenin_resistance(arms), rel=1e-9
    )


@pytest.mark.parametrize("arms,vs,rg", itertools.product(ARMS_SETS, [10.0, -6.0], [50.0, 470.0]))
def test_galvanometer_current_matches(arms, vs, rg):
    result = wheatstone_circuit.analyze(arms, vs, rg)
    assert result.galvanometer_current == pytest.approx(
        thevenin.galvanometer_current(arms, vs, rg), rel=1e-9
    )
    assert result.galvanometer_voltage == pytest.approx(
        thevenin.galvanometer_voltage(arms, vs, rg), rel=1e-9
    )


def test_balanced_bridge_zero_on_both_paths():
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=600.0)
    result = wheatstone_circuit.analyze(arms, 12.0, 150.0)
    assert result.open_circuit_voltage == 0.0
    assert result.galvanometer_current == 0.0
