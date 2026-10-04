"""双电桥参数校验：各类非法输入独立错误码，且都在求解前挡住。"""
import pytest

from app.bridge import kelvin_validation as kv
from app.validation import BridgeInputError

RATIO = {"R1": 100.0, "R2": 100.0, "r3": 10.0, "r4": 10.0}


def test_ratio_arm_errors_have_own_codes():
    with pytest.raises(BridgeInputError) as e:
        kv.require_ratio_arms({"R1": 0.0, "R2": 1.0, "r3": 1.0, "r4": 1.0})
    assert e.value.code == "kelvin_ratio_arm_not_positive"
    with pytest.raises(BridgeInputError) as e:
        kv.require_ratio_arms({"R1": float("nan"), "R2": 1.0, "r3": 1.0, "r4": 1.0})
    assert e.value.code == "kelvin_ratio_arm_not_finite"
    with pytest.raises(BridgeInputError) as e:
        kv.require_ratio_arms({"R1": 1.0, "R2": 1.0, "r3": 1.0})
    assert e.value.code == "kelvin_ratio_arm_missing"
    with pytest.raises(BridgeInputError) as e:
        kv.require_ratio_arms({**RATIO, "R9": 1.0})
    assert e.value.code == "kelvin_ratio_arm_unknown"


def test_standard_resistance_errors():
    with pytest.raises(BridgeInputError) as e:
        kv.require_standard_resistance(-1.0)
    assert e.value.code == "kelvin_standard_not_positive"
    with pytest.raises(BridgeInputError) as e:
        kv.require_standard_resistance(float("inf"))
    assert e.value.code == "kelvin_standard_not_finite"


def test_unknown_resistance_errors():
    with pytest.raises(BridgeInputError) as e:
        kv.require_unknown_resistance(0.0)
    assert e.value.code == "kelvin_unknown_not_positive"
    with pytest.raises(BridgeInputError) as e:
        kv.require_unknown_resistance(float("nan"))
    assert e.value.code == "kelvin_unknown_not_finite"


def test_yoke_negative_vs_nonfinite():
    assert kv.require_yoke_resistance(0.0) == 0.0  # 轭线为零允许
    with pytest.raises(BridgeInputError) as e:
        kv.require_yoke_resistance(-1e-9)
    assert e.value.code == "kelvin_yoke_negative"
    with pytest.raises(BridgeInputError) as e:
        kv.require_yoke_resistance(float("inf"))
    assert e.value.code == "kelvin_yoke_not_finite"


def test_contact_negative_vs_nonfinite_and_unknown():
    with pytest.raises(BridgeInputError) as e:
        kv.require_contacts({"rx_co_c": -0.001})
    assert e.value.code == "kelvin_contact_negative"
    with pytest.raises(BridgeInputError) as e:
        kv.require_contacts({"rs_pi_c": float("nan")})
    assert e.value.code == "kelvin_contact_not_finite"
    with pytest.raises(BridgeInputError) as e:
        kv.require_contacts({"bogus": 1.0})
    assert e.value.code == "kelvin_contact_unknown"
    # 缺省整体为零
    defaulted = kv.require_contacts(None)
    assert defaulted.as_dict()["rx_co_c"] == 0.0


def test_source_current_only_requires_finite():
    assert kv.require_source_current(0.0) == 0.0
    assert kv.require_source_current(-2.0) == -2.0
    with pytest.raises(BridgeInputError) as e:
        kv.require_source_current(float("nan"))
    assert e.value.code == "kelvin_source_current_not_finite"


def test_error_codes_are_distinct():
    codes = set()
    for call, code in [
        (lambda: kv.require_ratio_arms({"R2": 1, "r3": 1, "r4": 1}), "kelvin_ratio_arm_missing"),
        (lambda: kv.require_standard_resistance(0), "kelvin_standard_not_positive"),
        (lambda: kv.require_unknown_resistance(0), "kelvin_unknown_not_positive"),
        (lambda: kv.require_yoke_resistance(-1), "kelvin_yoke_negative"),
        (lambda: kv.require_contacts({"rx_co_c": -1}), "kelvin_contact_negative"),
        (lambda: kv.require_source_current(float("inf")), "kelvin_source_current_not_finite"),
    ]:
        with pytest.raises(BridgeInputError) as e:
            call()
        assert e.value.code == code
        codes.add(code)
    assert len(codes) == 6
