"""开尔文双电桥正算（节点方程）判据。

- 反推出的 Rx 代回正算：开路输出与检流计电流均归零（多组参数）；
- 接触电阻作为独立元件进节点方程（与闭式有效臂归并结果一致）；
- 手算基准钉死；恒流源翻倍 ⇒ 输出翻倍；零源为零；
- 检流计电流与戴维南等效自洽（Ig = Vth/(Rth+Rg)）。
"""
import itertools

import pytest

from app.bridge import kelvin_balance, kelvin_forward
from app.bridge.kelvin_topology import KelvinConfig, KelvinContacts

BENCH = KelvinConfig(200.0, 200.0, 20.0, 20.0, 0.05, 0.01)


def test_benchmark_zero_output_pinned():
    """手算基准：等比例、轭线非零，Rx=0.05 时开路严格为零。"""
    assert kelvin_forward.open_circuit_voltage(BENCH, 0.05, 1.0) == pytest.approx(0.0, abs=1e-14)


@pytest.mark.parametrize(
    "cfg",
    [
        KelvinConfig(100.0, 100.0, 10.0, 10.0, 0.1, 0.02),
        KelvinConfig(100.0, 100.0, 5.0, 10.0, 0.1, 0.01),
        KelvinConfig(200.0, 100.0, 20.0, 10.0, 0.001, 0.05),
        KelvinConfig(100.0, 100.0, 10.0, 10.0, 0.1, 1.0),
    ],
)
@pytest.mark.parametrize("rg", [None, 50.0, 470.0])
def test_solved_rx_plugged_back_gives_zero(cfg, rg):
    """闭式反推出的 Rx 代回节点正算，开路输出与检流计电流都必须归零。"""
    rx = kelvin_balance.solve_rx(cfg).rx
    result = kelvin_forward.analyze(cfg, rx, 1.0, rg)
    assert result.open_circuit_voltage == pytest.approx(0.0, abs=1e-12)
    if rg is not None:
        assert result.galvanometer_current == pytest.approx(0.0, abs=1e-13)


def test_contacts_as_separate_elements_match_closed_form():
    """含全部 8 个接触电阻时，节点正算的平衡点仍与闭式有效臂归并一致。"""
    contacts = KelvinContacts(
        rx_co_c=3e-3, rx_ci_c=2e-3, rx_po_c=0.4, rx_pi_c=0.02,
        rs_co_c=4e-3, rs_ci_c=1e-3, rs_po_c=0.3, rs_pi_c=0.01,
    )
    cfg = KelvinConfig(100.0, 100.0, 10.0, 10.0, 0.1, 0.02, contacts)
    rx = kelvin_balance.solve_rx(cfg).rx
    result = kelvin_forward.analyze(cfg, rx, 1.0, 50.0)
    assert result.open_circuit_voltage == pytest.approx(0.0, abs=1e-12)
    assert result.galvanometer_current == pytest.approx(0.0, abs=1e-13)


def test_current_contact_only_does_not_move_nodal_balance():
    """节点方程层面：仅加待测两电流端接触电阻，原平衡点输出仍为零。"""
    cfg = KelvinConfig(
        100.0, 100.0, 10.0, 10.0, 0.1, 0.02,
        KelvinContacts(rx_co_c=5e-3, rx_ci_c=2e-3),
    )
    assert kelvin_forward.open_circuit_voltage(cfg, 0.1, 1.0) == pytest.approx(0.0, abs=1e-14)


def test_galvanometer_current_follows_thevenin_equivalent():
    """检流计电流满足 Ig = Vth/(Rth+Rg)，且 Rg→∞ 时端电压→开路电压。"""
    cfg = KelvinConfig(100.0, 100.0, 5.0, 10.0, 0.1, 0.02)
    rx = 0.12
    v_th = kelvin_forward.open_circuit_voltage(cfg, rx, 1.0)
    r_th = kelvin_forward.thevenin_resistance(cfg, rx)
    result = kelvin_forward.analyze(cfg, rx, 1.0, 150.0)
    assert v_th != 0.0
    assert result.galvanometer_current == pytest.approx(v_th / (r_th + 150.0), rel=1e-9)
    assert result.galvanometer_voltage == pytest.approx(
        result.galvanometer_current * 150.0, rel=1e-9
    )
    # 大内阻极限：检流计端电压趋近开路电压
    big = kelvin_forward.analyze(cfg, rx, 1.0, 1e12)
    assert big.galvanometer_voltage == pytest.approx(v_th, rel=1e-6)


def test_output_scales_linearly_with_source_current():
    cfg = KelvinConfig(100.0, 100.0, 5.0, 10.0, 0.1, 0.02)
    v1 = kelvin_forward.open_circuit_voltage(cfg, 0.12, 1.0)
    v2 = kelvin_forward.open_circuit_voltage(cfg, 0.12, -2.5)
    assert v1 != 0.0
    assert v2 == pytest.approx(-2.5 * v1, rel=1e-12)


def test_zero_source_gives_zero_output():
    cfg = KelvinConfig(100.0, 100.0, 5.0, 10.0, 0.1, 0.02)
    result = kelvin_forward.analyze(cfg, 0.12, 0.0, 50.0)
    assert result.open_circuit_voltage == 0.0
    assert result.galvanometer_current == 0.0
