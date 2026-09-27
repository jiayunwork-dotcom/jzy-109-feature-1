"""正算（开路输出）判据：平衡为零、符号翻转、桥源翻倍、手算基准。"""
import pytest

from app.bridge import forward
from app.bridge.topology import ArmSet

#: 预置手算基准：四臂相等
BENCH = ArmSet(r1=1000.0, r2=1000.0, r3=1000.0, r4=1000.0)


def test_all_equal_benchmark_output_zero():
    """四臂相等的手算基准：V_B = V_D = Vs/2，输出恰为零。"""
    assert forward.divider_voltage_b(BENCH, 10.0) == 5.0
    assert forward.divider_voltage_d(BENCH, 10.0) == 5.0
    assert forward.open_circuit_output(BENCH, 10.0) == 0.0


def test_opposite_products_equal_output_zero():
    """相对臂乘积相等（100·600 = 200·300）时开路输出必须为零。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=600.0)
    assert forward.open_circuit_output(arms, 12.0) == 0.0


def test_hand_computable_unbalanced_case():
    """可手算核对的失衡例：V_B = 12·300/400 = 9，V_D = 12·100/300 = 4，输出 5 V。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=100.0)
    assert forward.divider_voltage_b(arms, 12.0) == 9.0
    assert forward.divider_voltage_d(arms, 12.0) == 4.0
    assert forward.open_circuit_output(arms, 12.0) == 5.0


def test_source_doubling_doubles_output_magnitude():
    """桥源电压放大一倍，同一失衡程度下输出绝对值随之放大一倍。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=500.0)
    v1 = forward.open_circuit_output(arms, 6.0)
    v2 = forward.open_circuit_output(arms, 12.0)
    assert v1 != 0.0
    assert abs(v2) == pytest.approx(2.0 * abs(v1), rel=1e-15)


def test_sign_flips_across_balance_point():
    """固定其它三臂、单独增大待测臂 r4：输出单调变化并在平衡点处符号翻转。"""
    vs = 10.0

    def out(r4: float) -> float:
        return forward.open_circuit_output(ArmSet(100.0, 100.0, 100.0, r4), vs)

    assert out(90.0) > 0.0
    assert out(100.0) == 0.0
    assert out(110.0) < 0.0
    sweep = [out(r4) for r4 in (80.0, 90.0, 100.0, 110.0, 120.0)]
    assert all(a > b for a, b in zip(sweep, sweep[1:]))


def test_zero_source_gives_zero_output_not_error():
    """桥源为零是正常情形：输出为零，不抛异常。"""
    arms = ArmSet(r1=100.0, r2=200.0, r3=300.0, r4=500.0)
    assert forward.open_circuit_output(arms, 0.0) == 0.0
