"""平衡反解判据：闭式解逐臂核对、反解代回正算归零的自洽闭合。"""
import pytest

from app.bridge import balance, forward
from app.bridge.topology import ARM_NAMES, ArmSet

#: 一套满足平衡的完整四臂：120·2275 = 273000 = 350·780
BALANCED = ArmSet(r1=120.0, r2=350.0, r3=780.0, r4=2275.0)


def test_balance_condition_is_opposite_products():
    """平衡条件必须是相对臂乘积相等：R1·R4 = R2·R3。"""
    assert balance.BALANCE_CONDITION == "r1*r4 = r2*r3"
    left, right = balance.balance_products(BALANCED)
    assert left == right == 273000.0
    assert balance.is_balanced(BALANCED)
    # 相邻臂相等但相对臂不等时不平衡（防止错写成相邻臂判据）
    adjacent_equal = ArmSet(r1=100.0, r2=100.0, r3=300.0, r4=500.0)
    assert not balance.is_balanced(adjacent_equal)


def test_solve_each_arm_roundtrip():
    """每个臂都能由其余三臂闭式解出，且解回原值。"""
    for name in ARM_NAMES:
        known = {n: getattr(BALANCED, n) for n in ARM_NAMES if n != name}
        solved, formula = balance.solve_unknown_arm(name, known)
        assert solved == pytest.approx(getattr(BALANCED, name), rel=1e-12)
        assert formula.startswith(f"{name} = ")


def test_closure_solved_arm_plugged_back_gives_zero_output():
    """自洽闭合：反解出的待测臂代回正算，输出必须归零。"""
    known = {"r1": 100.0, "r2": 200.0, "r3": 300.0}
    r4, _ = balance.solve_unknown_arm("r4", known)
    assert r4 == 600.0  # 手算：200·300/100
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=r4)
    assert forward.open_circuit_output(arms, 12.0) == 0.0
    assert balance.is_balanced(arms)


@pytest.mark.parametrize(
    "known, unknown",
    [
        ({"r1": 47.5, "r2": 1230.0, "r3": 86.4}, "r4"),
        ({"r2": 10.0, "r3": 999.9, "r4": 0.5}, "r1"),
        ({"r1": 3.3e3, "r3": 0.75, "r4": 91.0}, "r2"),
        ({"r1": 2.2, "r2": 4.4e4, "r4": 8.8}, "r3"),
    ],
)
def test_closure_parametrized(known, unknown):
    """多组取值（含大小悬殊阻值）下，反解代回正算输出均归零。"""
    solved, _ = balance.solve_unknown_arm(unknown, known)
    arms = ArmSet(**{**known, unknown: solved})
    assert forward.open_circuit_output(arms, 7.5) == pytest.approx(0.0, abs=1e-9)
    assert balance.is_balanced(arms)
