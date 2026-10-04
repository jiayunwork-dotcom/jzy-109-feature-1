"""参数校验：在计算之前挡住非法输入，并用带原因的响应讲清问题。

所有校验失败都抛出 BridgeInputError，由 HTTP 层统一转成
{"error": {"code": ..., "message": ...}} 的响应，绝不让求解跑到
中途才因除零等问题报出难懂的异常。
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.bridge.kelvin_topology import CONTACT_FIELDS, KelvinBridge
from app.bridge.topology import ARM_NAMES, ArmSet
from app.presets import BRIDGE_TYPES, KELVIN, WHEATSTONE


class BridgeInputError(ValueError):
    """非法输入。code 供机器判断，message 面向操作人员。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _require_positive_finite(label: str, value: Any, code_prefix: str) -> float:
    if not _is_finite_number(value):
        raise BridgeInputError(
            f"{code_prefix}_not_finite", f"{label} 必须是有限数值，收到 {value!r}"
        )
    if value <= 0:
        raise BridgeInputError(
            f"{code_prefix}_not_positive", f"{label} 必须为正数，收到 {value}"
        )
    return float(value)


def require_arm_set(raw: Any) -> ArmSet:
    """校验并构造四臂集合：缺项、多出不认识的臂、非正、非有限都在此挡住。"""
    if not isinstance(raw, Mapping):
        raise BridgeInputError(
            "arms_invalid", "arms 必须是形如 {\"r1\": .., \"r2\": .., \"r3\": .., \"r4\": ..} 的对象"
        )
    names = set(raw)
    missing = [n for n in ARM_NAMES if n not in names]
    if missing:
        raise BridgeInputError("arm_missing", f"桥臂缺项：{', '.join(missing)}")
    extra = sorted(names - set(ARM_NAMES))
    if extra:
        raise BridgeInputError(
            "arm_unknown", f"未知桥臂：{', '.join(extra)}；合法臂名为 r1、r2、r3、r4"
        )
    values = {
        n: _require_positive_finite(f"桥臂 {n} 阻值", raw[n], "arm") for n in ARM_NAMES
    }
    return ArmSet(**values)


def validate_source_voltage(value: Any) -> float:
    """桥源电压只要求是有限的数。

    零是正常情形（输出为零，由上层标明，不算错误）；负值表示桥源
    极性反接，是实验室消除热电势的常用做法，同样允许。
    """
    if not _is_finite_number(value):
        raise BridgeInputError(
            "source_voltage_not_finite", f"桥源电压必须是有限数值，收到 {value!r}"
        )
    return float(value)


def validate_galvanometer(value: Any) -> float | None:
    """检流计内阻：可不提供（开路），提供则必须为正有限值。"""
    if value is None:
        return None
    return _require_positive_finite("检流计内阻", value, "galvanometer")


def validate_unknown_arm(name: Any) -> str:
    if name not in ARM_NAMES:
        raise BridgeInputError(
            "solve_unknown_arm_invalid",
            f"待求臂必须是 r1、r2、r3、r4 之一，收到 {name!r}",
        )
    return name


def validate_known_arms(unknown_arm: str, raw: Any) -> dict[str, float]:
    """反推时的已知三臂：必须恰好是待求臂之外的三臂，且均为正有限值。"""
    expected = {n for n in ARM_NAMES if n != unknown_arm}
    if not isinstance(raw, Mapping):
        raise BridgeInputError(
            "solve_known_arms_missing",
            f"反推需要给出除 {unknown_arm} 外的三个已知臂：{', '.join(sorted(expected))}",
        )
    names = set(raw)
    if unknown_arm in names:
        raise BridgeInputError(
            "solve_target_inconsistent",
            f"目标不自洽：{unknown_arm} 被指定为待求臂，却又出现在已知臂中",
        )
    missing = sorted(expected - names)
    extra = sorted(names - expected)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"缺少已知臂 {', '.join(missing)}")
        if extra:
            parts.append(f"多出不认识的臂 {', '.join(extra)}")
        raise BridgeInputError(
            "solve_known_arms_mismatch",
            "；".join(parts) + f"；反推 {unknown_arm} 需要且仅需要 {', '.join(sorted(expected))}",
        )
    return {
        n: _require_positive_finite(f"桥臂 {n} 阻值", raw[n], "arm") for n in sorted(expected)
    }


def validate_solve_target(target: Any) -> None:
    """反推接口只接受平衡目标（输出为零）；其它目标与平衡条件不自洽。"""
    if target is None:
        return
    if not _is_finite_number(target) or target != 0.0:
        raise BridgeInputError(
            "solve_target_inconsistent",
            f"目标不自洽：本接口按平衡条件反推，目标输出必须为 0，收到 {target!r}",
        )


# --------------------------------------------------------------------------
# 开尔文双电桥校验
# --------------------------------------------------------------------------

#: 反解不需要 rx；正算时 rx 必须为正
_KELVIN_ARM_FIELDS: tuple[str, ...] = ("r1", "r2", "r3", "r4")
_KELVIN_POSITIVE_FIELDS: dict[str, str] = {
    "rs": "标准电阻 rs",
    "r1": "外比例臂 r1",
    "r2": "外比例臂 r2",
    "r3": "内比例臂 r3",
    "r4": "内比例臂 r4",
}


def _require_nonneg_finite(label: str, value: Any, field: str) -> float:
    """轭线/接触电阻：允许为零，但不得为负或非有限。"""
    if not _is_finite_number(value):
        raise BridgeInputError(
            f"{field}_not_finite", f"{label} 必须是有限数值，收到 {value!r}"
        )
    if value < 0:
        raise BridgeInputError(
            f"{field}_negative", f"{label} 必须非负，收到 {value}"
        )
    return float(value)


def validate_preset_type(value: Any) -> str:
    """电桥档类型：缺省（老式登记）按四臂惠斯通电桥处理。"""
    if value is None:
        return WHEATSTONE
    if value not in BRIDGE_TYPES:
        raise BridgeInputError(
            "bridge_type_invalid",
            f"电桥类型必须是 {WHEATSTONE!r} 或 {KELVIN!r}，收到 {value!r}",
        )
    return value


def require_kelvin_bridge(raw: Any, *, need_rx: bool) -> KelvinBridge:
    """校验并构造双电桥参数。need_rx 控制是否要求待测电阻 rx（正算要，反解不要）。

    错误码彼此独立、在求解节点方程之前挡住：
    ``kelvin_arm_not_positive``（比例臂/标准电阻/待测电阻非正或非有限）、
    ``kelvin_yoke_negative``（轭线为负或非有限）、
    ``kelvin_contact_negative``（任一接触电阻为负或非有限）、
    ``kelvin_field_unknown``（多出不认识的字段）。
    """
    if not isinstance(raw, Mapping):
        raise BridgeInputError(
            "kelvin_params_invalid",
            "双电桥参数必须是包含 r1、r2、r3、r4、rs（及可选 yoke、接触电阻）的对象",
        )

    required = set(_KELVIN_POSITIVE_FIELDS)
    known = required | {"rx", "yoke"} | set(CONTACT_FIELDS)
    extra = sorted(set(raw) - known)
    if extra:
        raise BridgeInputError(
            "kelvin_field_unknown",
            f"双电桥参数出现未知字段：{', '.join(extra)}",
        )

    missing = sorted(required - set(raw))
    if missing:
        raise BridgeInputError(
            "kelvin_field_missing", f"双电桥参数缺少必填字段：{', '.join(missing)}"
        )

    values: dict[str, float] = {}
    for field, label in _KELVIN_POSITIVE_FIELDS.items():
        values[field] = _require_positive_finite(label, raw[field], "kelvin_arm")
    # rx：正算必填为正有限；反解/登记可给可省，给了也必须正有限
    if raw.get("rx") is not None:
        values["rx"] = _require_positive_finite("待测电阻 rx", raw["rx"], "kelvin_arm")
    else:
        if need_rx:
            raise BridgeInputError(
                "kelvin_field_missing", "双电桥正算必须给出待测电阻 rx"
            )
        values["rx"] = 0.0

    values["yoke"] = _require_nonneg_finite("轭线电阻 yoke", raw.get("yoke", 0.0), "kelvin_yoke")
    for field in CONTACT_FIELDS:
        label = {
            "rc1": "C1 电流端接触电阻 rc1", "rc2": "C2 电流端接触电阻 rc2",
            "rc3": "C3 电流端接触电阻 rc3", "rc4": "C4 电流端接触电阻 rc4",
            "rp1": "P1 电位端接触电阻 rp1", "rp2": "P2 电位端接触电阻 rp2",
            "rp3": "P3 电位端接触电阻 rp3", "rp4": "P4 电位端接触电阻 rp4",
        }[field]
        values[field] = _require_nonneg_finite(label, raw.get(field, 0.0), "kelvin_contact")

    return KelvinBridge(**values)


def validate_source_current(value: Any) -> float:
    """恒流源电流只要求是有限数。零是正常情形（输出为零），负号表示反向。"""
    if not _is_finite_number(value):
        raise BridgeInputError(
            "source_current_not_finite", f"恒流源电流必须是有限数值，收到 {value!r}"
        )
    return float(value)
