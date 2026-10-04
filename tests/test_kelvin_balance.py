"""开尔文双电桥闭式反推判据。

覆盖用户逐条核对项：
· 内外比例一致时轭线电阻任意变化（含远大于被测值）反推值不变；
· 比例失配时反推值随轭线线性变化，变化量等于闭式修正项；
· 电流端接触（比例一致）不动平衡；电位端接触偏移等于串进对应臂的闭式结果；
· 反推值代回双电桥节点正算，检流计电流归零；
· 手算基准（比例相等、轭线非零）钉入回归。
"""
import pytest

from app.bridge import kelvin_balance, kelvin_forward
from app.bridge.kelvin_topology import KelvinBridge

CLOSURE_CURRENT = 1.0
CLOSURE_RG = 50.0


def _check_closure(bridge_without_rx: KelvinBridge) -> tuple[float, float, float]:
    rx, main_term, correction = kelvin_balance.solve_unknown_rx(bridge_without_rx)
    full = KelvinBridge(**{**bridge_without_rx.as_dict(), "rx": rx})
    v_out = kelvin_forward.open_circuit_output(full, CLOSURE_CURRENT)
    i_g = kelvin_forward.galvanometer_current(full, CLOSURE_CURRENT, CLOSURE_RG)
    return rx, v_out, i_g


def test_formula_text_and_balance_condition():
    assert "rx = (r1/r2)*rs" in kelvin_balance.FORMULA


# ---- 手算可核基准（比例相等、轭线非零）----

def test_hand_computable_equal_ratio_benchmark():
    """rs=1 mΩ、内外比例都=1、轭线=2 mΩ 非零：rx=1·rs+0=1 mΩ，输出严格零。"""
    b = KelvinBridge(rx=0.0, rs=0.001, r1=1000, r2=1000, r3=300, r4=300, yoke=0.002)
    rx, main_term, correction = kelvin_balance.solve_unknown_rx(b)
    assert rx == pytest.approx(0.001)
    assert main_term == pytest.approx(0.001)
    assert correction == 0.0

    full = KelvinBridge(**{**b.as_dict(), "rx": rx})
    assert kelvin_forward.open_circuit_output(full, 1.0) == pytest.approx(0.0, abs=1e-18)
    assert kelvin_forward.galvanometer_current(full, 1.0, 50.0) == pytest.approx(0.0, abs=1e-18)


# ---- 轭线扫描 ----

def test_equal_ratio_yoke_sweep_does_not_move_balance():
    """内外比例一致：轭线从 0 调到远大于被测值（100 Ω），反推值严格不变。"""
    b = KelvinBridge(rx=0.0, rs=0.01, r1=1000, r2=1000, r3=300, r4=300)
    ref, _, _ = kelvin_balance.solve_unknown_rx(b)
    for yoke in (0.0, 1e-6, 1e-3, 0.1, 1.0, 10.0, 100.0):
        bi = KelvinBridge(**{**b.as_dict(), "yoke": yoke})
        rx, main_term, correction = kelvin_balance.solve_unknown_rx(bi)
        assert rx == pytest.approx(ref, abs=1e-15)
        assert correction == 0.0  # 内外比例一致时修正严格为零


def test_mismatched_ratio_correction_matches_closed_form():
    """比例失配：修正项随轭线线性变化，且就是闭式 Δ（含符号）。"""
    rs, r1, r2, r3, r4 = 0.01, 1000.0, 1000.0, 300.0, 200.0  # p=1, q=1.5
    p, q = r1 / r2, r3 / r4
    prev = None
    for yoke in (0.0, 0.001, 0.005, 0.02):
        b = KelvinBridge(rx=0.0, rs=rs, r1=r1, r2=r2, r3=r3, r4=r4, yoke=yoke)
        rx, main_term, correction = kelvin_balance.solve_unknown_rx(b)
        expected = yoke * (r1 * r4 - r2 * r3) / (r2 * (r3 + r4 + yoke))
        assert correction == pytest.approx(expected)
        # 主比例项恒为 p·rs
        assert main_term == pytest.approx(p * rs)
        # 相对更直观的比例形式：Δ = yoke·(p−q)·R4/(R3+R4+yoke)
        assert correction == pytest.approx(yoke * (p - q) * r4 / (r3 + r4 + yoke))
        if prev is not None:
            # yoke 增大（p−q<0）修正单调更负
            assert correction < prev
        prev = correction


def test_zero_yoke_correction_zero_even_when_mismatched():
    """即使内外比例失配，轭线为零时修正项也为零。"""
    b = KelvinBridge(rx=0.0, rs=0.01, r1=1000, r2=500, r3=300, r4=200, yoke=0.0)
    _, main_term, correction = kelvin_balance.solve_unknown_rx(b)
    assert correction == 0.0
    assert main_term == pytest.approx(0.02)


# ---- 接触电阻 ----

def test_current_end_contacts_do_not_move_balance_equal_ratio():
    """内外比例一致：只增大待测电阻两个电流端接触 rc1、rc2，平衡点不动。

    rc1 在恒流源支路（电流不变），rc2 与轭线串联但内外比例一致时 Δ=0。
    """
    b = KelvinBridge(rx=0.0, rs=0.01, r1=1000, r2=1000, r3=300, r4=300, yoke=0.002)
    ref, _, _ = kelvin_balance.solve_unknown_rx(b)
    for rc1, rc2 in ((0.001, 0.0), (0.01, 0.005), (0.1, 0.1)):
        bi = KelvinBridge(**{**b.as_dict(), "rc1": rc1, "rc2": rc2})
        rx, _, correction = kelvin_balance.solve_unknown_rx(bi)
        assert rx == pytest.approx(ref, abs=1e-15)
        assert correction == 0.0


def test_outer_current_contacts_never_move_balance_even_mismatched():
    """外侧电流端接触 rc1、rc4 在恒流源支路：即使比例失配也不移动平衡点。"""
    b = KelvinBridge(rx=0.0, rs=0.01, r1=1000, r2=500, r3=300, r4=200, yoke=0.002)
    ref, _, _ = kelvin_balance.solve_unknown_rx(b)
    bi = KelvinBridge(**{**b.as_dict(), "rc1": 0.5, "rc4": 0.7})
    rx, _, _ = kelvin_balance.solve_unknown_rx(bi)
    assert rx == pytest.approx(ref, abs=1e-15)


@pytest.mark.parametrize("field,arm_field", [
    ("rp1", "r1"), ("rp2", "r3"), ("rp3", "r2"), ("rp4", "r4"),
])
def test_potential_end_contact_matches_arm_in_series(field, arm_field):
    """只增大某个电位端接触：偏移量等于把它串进对应比例臂后的闭式结果。"""
    params = dict(rx=0.0, rs=0.01, r1=1000, r2=1000, r3=300, r4=300, yoke=0.002)
    contact = 0.37
    b = KelvinBridge(**{**params, field: contact})
    rx, _, _ = kelvin_balance.solve_unknown_rx(b)

    eff = dict(params)
    eff[arm_field] = eff[arm_field] + contact
    expected, _, _ = kelvin_balance.solve_unknown_rx(KelvinBridge(**eff))
    assert rx == pytest.approx(expected, rel=1e-12)

    # 节点正算在该 rx 下输出为零
    full = KelvinBridge(**{**b.as_dict(), "rx": rx})
    assert kelvin_forward.open_circuit_output(full, 1.0) == pytest.approx(0.0, abs=1e-15)


def test_inner_current_contacts_add_to_yoke_mismatched():
    """比例失配时 rc2、rc3 等价于增大轭线：闭式用 yoke+rc2+rc3。"""
    base = dict(rx=0.0, rs=0.01, r1=1000, r2=500, r3=300, r4=200, yoke=0.002)
    b_with_contacts = KelvinBridge(**{**base, "rc2": 0.001, "rc3": 0.002})
    b_equiv_yoke = KelvinBridge(**{**base, "yoke": 0.002 + 0.001 + 0.002})
    rx1, _, _ = kelvin_balance.solve_unknown_rx(b_with_contacts)
    rx2, _, _ = kelvin_balance.solve_unknown_rx(b_equiv_yoke)
    assert rx1 == pytest.approx(rx2, rel=1e-14)


# ---- 反推代回正算：检流计归零 ----

@pytest.mark.parametrize("rs,r1,r2,r3,r4,yoke", [
    (0.003, 1000, 2000, 300, 700, 0.002),
    (0.01, 1000, 1000, 300, 300, 0.005),
    (0.0008, 800, 2000, 300, 700, 0.0015),
    (1.0, 3.0, 5.0, 7.0, 11.0, 0.1),
    (0.005, 100, 100, 100, 100, 0.01),
])
def test_solved_rx_plugged_back_gives_zero_galvanometer(rs, r1, r2, r3, r4, yoke):
    """反推出的 rx 代回整桥节点正算：开路输出与检流计电流都归零。"""
    b = KelvinBridge(rx=0.0, rs=rs, r1=r1, r2=r2, r3=r3, r4=r4, yoke=yoke)
    rx, v_out, i_g = _check_closure(b)
    assert v_out == pytest.approx(0.0, abs=1e-12)
    assert i_g == pytest.approx(0.0, abs=1e-12)


def test_solved_rx_with_all_contacts_plugged_back_zero():
    """八个接触电阻都非零时，反推值代回节点正算仍然平衡。"""
    b = KelvinBridge(
        rx=0.0, rs=0.003, r1=1000, r2=2000, r3=300, r4=700, yoke=0.002,
        rc1=5e-3, rc2=1e-3, rc3=2e-3, rc4=7e-3,
        rp1=1e-3, rp2=2e-3, rp3=3e-3, rp4=4e-3,
    )
    rx, v_out, i_g = _check_closure(b)
    assert v_out == pytest.approx(0.0, abs=1e-14)
    assert i_g == pytest.approx(0.0, abs=1e-16)


# ---- 正算单调性/线性（节点方程路径）----

def test_output_sign_flips_and_scales_with_current():
    """固定其余参数、扫 rx：输出在闭式平衡点过零并翻号；电流翻倍输出翻倍。"""
    rs, r1, r2, r3, r4, yoke = 0.001, 1000.0, 1000.0, 300.0, 300.0, 0.002
    rx_bal, _, _ = kelvin_balance.solve_unknown_rx(
        KelvinBridge(0.0, rs, r1, r2, r3, r4, yoke)
    )

    def out(rx, current):
        b = KelvinBridge(rx, rs, r1, r2, r3, r4, yoke)
        return kelvin_forward.open_circuit_output(b, current)

    assert out(rx_bal * 0.5, 1.0) != 0.0
    assert out(rx_bal, 1.0) == pytest.approx(0.0, abs=1e-17)
    assert out(rx_bal * 1.5, 1.0) * out(rx_bal * 0.5, 1.0) < 0.0
    v1, v2 = out(rx_bal * 0.5, 1.0), out(rx_bal * 0.5, 2.0)
    assert v2 == pytest.approx(2 * v1, rel=1e-12)
