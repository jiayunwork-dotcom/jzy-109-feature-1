"""开尔文双电桥参数校验：计算前挡住非法输入，各类问题错误码互相独立。

非法情形与错误码（与四臂电桥错误码区分开）：
  kelvin_ratio_arm_not_finite / kelvin_ratio_arm_not_positive  比例臂
  kelvin_standard_not_finite / kelvin_standard_not_positive    标准电阻
  kelvin_unknown_not_finite / kelvin_unknown_not_positive      待测电阻（正算）
  kelvin_yoke_not_finite / kelvin_yoke_negative                轭线电阻
  kelvin_contact_not_finite / kelvin_contact_negative          接触电阻
  kelvin_source_current_not_finite                             恒流源电流
  （恒流源电流允许为零：输出为零属正常；允许负值：电流反向）
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.bridge.kelvin_topology import CONTACT_NAMES, RATIO_NAMES, KelvinConfig, KelvinContacts
from app.validation import BridgeInputError, _is_finite_number


def _check_finite(label: str, value: Any, code_finite: str) -> float:
    if not _is_finite_number(value):
        raise BridgeInputError(code_finite, f"{label} 必须是有限数值，收到 {value!r}")
    return float(value)


def _require_positive(label: str, value: Any, code_finite: str, code_positive: str) -> float:
    value = _check_finite(label, value, code_finite)
    if value <= 0:
        raise BridgeInputError(code_positive, f"{label} 必须为正数，收到 {value}")
    return value


def _require_nonnegative(label: str, value: Any, code_finite: str, code_negative: str) -> float:
    value = _check_finite(label, value, code_finite)
    if value < 0:
        raise BridgeInputError(code_negative, f"{label} 必须非负，收到 {value}")
    return value


def require_ratio_arms(raw: Any) -> dict[str, float]:
    """校验四只比例臂 R1、R2、r3、r4：必须齐备且为正有限值。"""
    if not isinstance(raw, Mapping):
        raise BridgeInputError(
            "kelvin_ratio_arms_invalid",
            "ratio_arms 必须是形如 {\"R1\": .., \"R2\": .., \"r3\": .., \"r4\": ..} 的对象",
        )
    names = set(raw)
    missing = [n for n in RATIO_NAMES if n not in names]
    if missing:
        raise BridgeInputError("kelvin_ratio_arm_missing", f"比例臂缺项：{', '.join(missing)}")
    extra = sorted(names - set(RATIO_NAMES))
    if extra:
        raise BridgeInputError(
            "kelvin_ratio_arm_unknown",
            f"未知比例臂：{', '.join(extra)}；合法臂名为 R1、R2、r3、r4",
        )
    return {
        n: _require_positive(
            f"比例臂 {n}", raw[n],
            "kelvin_ratio_arm_not_finite", "kelvin_ratio_arm_not_positive",
        )
        for n in RATIO_NAMES
    }


def require_standard_resistance(value: Any) -> float:
    return _require_positive(
        "标准电阻 Rs", value,
        "kelvin_standard_not_finite", "kelvin_standard_not_positive",
    )


def require_yoke_resistance(value: Any) -> float:
    """轭线电阻允许为零（等比例下修正项恒零），但不可为负。"""
    return _require_nonnegative(
        "轭线电阻 Ry", value,
        "kelvin_yoke_not_finite", "kelvin_yoke_negative",
    )


def require_unknown_resistance(value: Any) -> float:
    """正算时的待测电阻：必须为正有限值。"""
    return _require_positive(
        "待测电阻 Rx", value,
        "kelvin_unknown_not_finite", "kelvin_unknown_not_positive",
    )


def require_source_current(value: Any) -> float:
    """恒流源电流只要求有限：零给出零输出（正常），负值表示电流反向。"""
    return _check_finite("恒流源电流 I_s", value, "kelvin_source_current_not_finite")


def require_contacts(raw: Any) -> KelvinContacts:
    """校验 8 个端钮接触电阻：可整体缺省（按零），逐项必须非负有限。"""
    if raw is None:
        return KelvinContacts()
    if not isinstance(raw, Mapping):
        raise BridgeInputError(
            "kelvin_contacts_invalid",
            "contacts 必须是对象，键为 8 个端钮接触电阻名（缺省按 0）",
        )
    extra = sorted(set(raw) - set(CONTACT_NAMES))
    if extra:
        raise BridgeInputError(
            "kelvin_contact_unknown",
            f"未知接触电阻端：{', '.join(extra)}；合法端名为 {', '.join(CONTACT_NAMES)}",
        )
    values = {
        name: _require_nonnegative(
            f"接触电阻 {name}", raw.get(name, 0.0),
            "kelvin_contact_not_finite", "kelvin_contact_negative",
        )
        for name in CONTACT_NAMES
    }
    return KelvinContacts(**values)


def build_config(
    ratio_arms: Any,
    standard_resistance: Any,
    yoke_resistance: Any,
    contacts: Any = None,
) -> KelvinConfig:
    """从请求字段构造经校验的双电桥固定参数。"""
    arms = require_ratio_arms(ratio_arms)
    rs = require_standard_resistance(standard_resistance)
    ry = require_yoke_resistance(yoke_resistance)
    ct = require_contacts(contacts)
    return KelvinConfig(
        R1=arms["R1"], R2=arms["R2"], r3=arms["r3"], r4=arms["r4"],
        Rs=rs, Ry=ry, contacts=ct,
    )
