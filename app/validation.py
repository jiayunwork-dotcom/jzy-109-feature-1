"""参数校验：在计算之前挡住非法输入，并用带原因的响应讲清问题。

所有校验失败都抛出 BridgeInputError，由 HTTP 层统一转成
{"error": {"code": ..., "message": ...}} 的响应，绝不让求解跑到
中途才因除零等问题报出难懂的异常。
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.bridge.topology import ARM_NAMES, ArmSet


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
