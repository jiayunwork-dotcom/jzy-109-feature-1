"""参数校验：各类非法输入在计算前被挡住，且错误码可区分。"""
import pytest

from app import validation
from app.validation import BridgeInputError


def _code(excinfo) -> str:
    return excinfo.value.code


def test_arm_not_positive_rejected():
    with pytest.raises(BridgeInputError) as e:
        validation.require_arm_set({"r1": 100.0, "r2": 0.0, "r3": 1.0, "r4": 2.0})
    assert _code(e) == "arm_not_positive"
    with pytest.raises(BridgeInputError) as e:
        validation.require_arm_set({"r1": 100.0, "r2": 1.0, "r3": -5.0, "r4": 2.0})
    assert _code(e) == "arm_not_positive"


def test_arm_missing_rejected():
    with pytest.raises(BridgeInputError) as e:
        validation.require_arm_set({"r1": 1.0, "r2": 1.0, "r3": 1.0})
    assert _code(e) == "arm_missing"
    assert "r4" in str(e.value)


def test_arm_unknown_and_non_finite_rejected():
    with pytest.raises(BridgeInputError) as e:
        validation.require_arm_set({"r1": 1.0, "r2": 1.0, "r3": 1.0, "r4": 1.0, "r5": 1.0})
    assert _code(e) == "arm_unknown"
    for bad in (float("nan"), float("inf")):
        with pytest.raises(BridgeInputError) as e:
            validation.require_arm_set({"r1": bad, "r2": 1.0, "r3": 1.0, "r4": 1.0})
        assert _code(e) == "arm_not_finite"


def test_source_voltage_zero_and_negative_allowed_non_finite_rejected():
    assert validation.validate_source_voltage(0.0) == 0.0
    assert validation.validate_source_voltage(-3.3) == -3.3
    with pytest.raises(BridgeInputError) as e:
        validation.validate_source_voltage(float("nan"))
    assert _code(e) == "source_voltage_not_finite"


def test_galvanometer_optional_but_positive():
    assert validation.validate_galvanometer(None) is None
    assert validation.validate_galvanometer(50.0) == 50.0
    with pytest.raises(BridgeInputError) as e:
        validation.validate_galvanometer(0.0)
    assert _code(e) == "galvanometer_not_positive"


def test_solve_inconsistent_targets():
    # 待求臂同时出现在已知臂中
    with pytest.raises(BridgeInputError) as e:
        validation.validate_known_arms("r4", {"r1": 1.0, "r2": 1.0, "r3": 1.0, "r4": 9.0})
    assert _code(e) == "solve_target_inconsistent"
    # 已知臂数量不对
    with pytest.raises(BridgeInputError) as e:
        validation.validate_known_arms("r4", {"r1": 1.0, "r2": 1.0})
    assert _code(e) == "solve_known_arms_mismatch"
    # 非零目标输出与平衡反推不自洽
    with pytest.raises(BridgeInputError) as e:
        validation.validate_solve_target(0.5)
    assert _code(e) == "solve_target_inconsistent"
    # 非法待求臂名
    with pytest.raises(BridgeInputError) as e:
        validation.validate_unknown_arm("r5")
    assert _code(e) == "solve_unknown_arm_invalid"


def test_solve_known_arms_ok():
    known = validation.validate_known_arms("r4", {"r1": 1.0, "r2": 2.0, "r3": 3.0})
    assert known == {"r1": 1.0, "r2": 2.0, "r3": 3.0}
    validation.validate_solve_target(None)
    validation.validate_solve_target(0.0)
