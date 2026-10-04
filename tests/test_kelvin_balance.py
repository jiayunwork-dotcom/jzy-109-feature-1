"""开尔文双电桥反推（闭式）判据。

覆盖：
- 内外比例一致时，轭线电阻从 0 调到远大于 Rx，反推值不变；
- 比例失配时，反推值随轭线电阻变化，变化量等于闭式修正项；
- 只增大两个电流端接触电阻，平衡点不动；
- 只增大某个电位端接触电阻，偏移等于把该电阻串进对应比例臂的闭式结果；
- 手算基准算例（比例相等、轭线非零）。
"""
import pytest

from app.bridge import kelvin_balance
from app.bridge.kelvin_topology import KelvinConfig, KelvinContacts


def test_equal_ratio_correction_is_strictly_zero():
    cfg = KelvinConfig(R1=100.0, R2=100.0, r3=10.0, r4=10.0, Rs=0.1, Ry=0.02)
    result = kelvin_balance.solve_rx(cfg)
    assert result.correction_term == 0.0
    assert result.rx == pytest.approx(0.1)


def test_equal_ratio_rx_invariant_as_yoke_sweeps_above_rx():
    """轭线电阻从 0 调到明显大于 Rx（10 Ω ≫ 0.001 Ω），反推值严格不变。"""
    values = []
    for ry in (0.0, 1e-5, 1e-3, 0.1, 1.0, 10.0):
        cfg = KelvinConfig(200.0, 100.0, 20.0, 10.0, 0.001, ry)
        values.append(kelvin_balance.solve_rx(cfg).rx)
    for value in values:
        assert value == pytest.approx(values[0], abs=1e-15)
    assert values[0] == pytest.approx(0.002)  # (R1/R2)·Rs = 2·0.001


def test_mismatched_ratio_correction_grows_with_yoke():
    """比例失配（R1/R2=1，r3/r4=0.5）：反推值随轭线电阻变化，与闭式修正一致。"""
    rxs = []
    for ry in (0.0, 0.01, 0.05, 0.1):
        cfg = KelvinConfig(100.0, 100.0, 5.0, 10.0, 0.1, ry)
        result = kelvin_balance.solve_rx(cfg)
        rxs.append(result.rx)
        # 手算修正：Ry·(R1·r4−R2·r3) / [R2·(r3+r4+Ry)]
        manual_corr = ry * (100.0 * 10.0 - 100.0 * 5.0) / (100.0 * (5.0 + 10.0 + ry))
        assert result.correction_term == pytest.approx(manual_corr, rel=1e-12)
        assert result.rx == pytest.approx(0.1 + manual_corr, rel=1e-12)
    assert rxs[0] == pytest.approx(0.1)  # Ry=0 时无论比例如何修正都为零
    assert all(b > a for a, b in zip(rxs, rxs[1:]))  # 随轭线电阻单调增大


def test_current_contact_resistances_do_not_move_balance():
    """只增大待测电阻两个电流端接触电阻（含外侧）：反推值不变。"""
    base = KelvinConfig(100.0, 100.0, 10.0, 10.0, 0.1, 0.02)
    with_contacts = KelvinConfig(
        100.0, 100.0, 10.0, 10.0, 0.1, 0.02,
        KelvinContacts(rx_co_c=5e-3, rx_ci_c=2e-3),
    )
    assert kelvin_balance.solve_rx(with_contacts).rx == pytest.approx(
        kelvin_balance.solve_rx(base).rx, abs=1e-15
    )
    # 四个电流端接触电阻全加（标准侧也加），等比例下仍不动
    all_current = KelvinConfig(
        100.0, 100.0, 10.0, 10.0, 0.1, 0.02,
        KelvinContacts(rx_co_c=9e-3, rx_ci_c=8e-3, rs_co_c=7e-3, rs_ci_c=6e-3),
    )
    assert kelvin_balance.solve_rx(all_current).rx == pytest.approx(0.1, abs=1e-15)


def test_potential_contact_enters_its_ratio_arm():
    """只增大某电位端接触电阻：偏移量 = 把该电阻串进对应比例臂的闭式结果。"""
    base_ry = 0.02
    # 待测外侧电位端：R1' = R1 + 0.5
    cfg = KelvinConfig(
        100.0, 100.0, 10.0, 10.0, 0.1, base_ry,
        KelvinContacts(rx_po_c=0.5),
    )
    result = kelvin_balance.solve_rx(cfg)
    r1e, r2e, r3e, r4e, rye = 100.5, 100.0, 10.0, 10.0, base_ry
    manual = (
        r1e / r2e * 0.1
        + rye * (r1e * r4e - r2e * r3e) / (r2e * (r3e + r4e + rye))
    )
    assert result.rx == pytest.approx(manual, rel=1e-12)
    assert result.rx != pytest.approx(0.1)  # 平衡点确实发生了偏移

    # 标准内侧电位端：r4' = r4 + 0.05
    cfg2 = KelvinConfig(
        100.0, 100.0, 10.0, 10.0, 0.1, base_ry,
        KelvinContacts(rs_pi_c=0.05),
    )
    result2 = kelvin_balance.solve_rx(cfg2)
    r1e, r2e, r3e, r4e = 100.0, 100.0, 10.0, 10.05
    manual2 = (
        r1e / r2e * 0.1
        + rye * (r1e * r4e - r2e * r3e) / (r2e * (r3e + r4e + rye))
    )
    assert result2.rx == pytest.approx(manual2, rel=1e-12)


def test_hand_computable_benchmark_pinned():
    """手算基准（比例相等、轭线非零）：R1=R2=200, r3=r4=20, Rs=0.05, Ry=0.01。

    内外比例都为 1，修正项严格为零，Rx = 1·0.05 = 0.05 Ω。
    """
    cfg = KelvinConfig(200.0, 200.0, 20.0, 20.0, 0.05, 0.01)
    result = kelvin_balance.solve_rx(cfg)
    assert result.main_term == pytest.approx(0.05)
    assert result.correction_term == 0.0
    assert result.rx == 0.05


def test_formula_text_contains_main_and_correction():
    assert "R1_eff/R2_eff" in kelvin_balance.FORMULA
    assert "yoke_eff" in kelvin_balance.FORMULA
