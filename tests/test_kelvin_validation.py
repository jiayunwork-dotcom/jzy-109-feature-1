"""双电桥参数校验：各类非法输入在求解前挡住，错误码彼此独立。"""
import math

import pytest

from app import validation
from app.validation import BridgeInputError

BASE = {"rs": 0.001, "r1": 1000, "r2": 1000, "r3": 300, "r4": 300, "yoke": 0.002}


def test_ratio_arms_and_standard_must_be_positive():
    for field in ("r1", "r2", "r3", "r4", "rs"):
        with pytest.raises(BridgeInputError) as e:
            validation.require_kelvin_bridge({**BASE, field: 0.0}, need_rx=False)
        assert e.value.code == "kelvin_arm_not_positive"
        with pytest.raises(BridgeInputError) as e:
            validation.require_kelvin_bridge({**BASE, field: -1.0}, need_rx=False)
        assert e.value.code == "kelvin_arm_not_positive"
        with pytest.raises(BridgeInputError) as e:
            validation.require_kelvin_bridge({**BASE, field: float("nan")}, need_rx=False)
        assert e.value.code == "kelvin_arm_not_finite"


def test_forward_requires_rx_positive():
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge(BASE, need_rx=True)
    assert e.value.code == "kelvin_field_missing"
    validation.require_kelvin_bridge({**BASE, "rx": 0.001}, need_rx=True)  # 不抛
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge({**BASE, "rx": -0.001}, need_rx=True)
    assert e.value.code == "kelvin_arm_not_positive"


def test_solve_allows_omitting_rx_but_rejects_bad_rx():
    validation.require_kelvin_bridge(BASE, need_rx=False)  # 无 rx 合法
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge({**BASE, "rx": 0.0}, need_rx=False)
    assert e.value.code == "kelvin_arm_not_positive"


def test_yoke_must_be_non_negative_finite():
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge({**BASE, "yoke": -0.001}, need_rx=False)
    assert e.value.code == "kelvin_yoke_negative"
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge({**BASE, "yoke": float("inf")}, need_rx=False)
    assert e.value.code == "kelvin_yoke_not_finite"


def test_contacts_must_be_non_negative_finite_independently():
    for field in ("rc1", "rc2", "rc3", "rc4", "rp1", "rp2", "rp3", "rp4"):
        with pytest.raises(BridgeInputError) as e:
            validation.require_kelvin_bridge({**BASE, field: -1e-9}, need_rx=False)
        assert e.value.code == "kelvin_contact_negative", field
        with pytest.raises(BridgeInputError) as e:
            validation.require_kelvin_bridge({**BASE, field: float("nan")}, need_rx=False)
        assert e.value.code == "kelvin_contact_not_finite", field


def test_zero_contacts_and_yoke_allowed():
    b = validation.require_kelvin_bridge({**BASE, "yoke": 0.0}, need_rx=False)
    assert b.yoke == 0.0
    assert all(getattr(b, f) == 0.0 for f in
               ("rc1", "rc2", "rc3", "rc4", "rp1", "rp2", "rp3", "rp4"))


def test_unknown_and_missing_fields():
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge({**BASE, "nope": 1.0}, need_rx=False)
    assert e.value.code == "kelvin_field_unknown"
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge({k: v for k, v in BASE.items() if k != "r2"},
                                         need_rx=False)
    assert e.value.code == "kelvin_field_missing"


def test_not_a_mapping():
    with pytest.raises(BridgeInputError) as e:
        validation.require_kelvin_bridge([1, 2, 3], need_rx=False)
    assert e.value.code == "kelvin_params_invalid"


def test_source_current_validation():
    assert validation.validate_source_current(0.0) == 0.0
    assert validation.validate_source_current(-2.5) == -2.5
    for bad in (float("nan"), float("inf"), float("-inf"), "1A", None):
        with pytest.raises(BridgeInputError) as e:
            validation.validate_source_current(bad)
        assert e.value.code == "source_current_not_finite"


def test_preset_type_validation():
    assert validation.validate_preset_type(None) == "wheatstone"
    assert validation.validate_preset_type("kelvin") == "kelvin"
    assert validation.validate_preset_type("wheatstone") == "wheatstone"
    with pytest.raises(BridgeInputError) as e:
        validation.validate_preset_type("maxwell")
    assert e.value.code == "bridge_type_invalid"
