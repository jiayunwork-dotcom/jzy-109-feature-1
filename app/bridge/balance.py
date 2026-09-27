"""平衡条件与待测臂反推（闭式解）。

平衡条件（相对臂/对角臂乘积相等）：
    R1·R4 = R2·R3

由此得任一臂关于其余三臂的闭式解——待求臂 = 另一对对角臂之积 ÷ 自身对角伙伴：
    R1 = R2·R3/R4     R2 = R1·R4/R3
    R3 = R1·R4/R2     R4 = R2·R3/R1
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from app.bridge.topology import ArmSet

#: 平衡条件的规范文本，接口响应中回显
BALANCE_CONDITION = "r1*r4 = r2*r3"

#: 待求臂 -> (另一对对角臂, 另一对对角臂, 自身对角伙伴)
_FORMULAS: dict[str, tuple[str, str, str]] = {
    "r1": ("r2", "r3", "r4"),
    "r2": ("r1", "r4", "r3"),
    "r3": ("r1", "r4", "r2"),
    "r4": ("r2", "r3", "r1"),
}


def balance_products(arms: ArmSet) -> tuple[float, float]:
    """两对相对臂的乘积 (R1·R4, R2·R3)；相等则桥平衡。"""
    return arms.r1 * arms.r4, arms.r2 * arms.r3


def is_balanced(arms: ArmSet, rel_tol: float = 1e-9) -> bool:
    """按相对臂乘积是否相等判定平衡（相对容差默认 1e-9）。"""
    left, right = balance_products(arms)
    return math.isclose(left, right, rel_tol=rel_tol, abs_tol=0.0)


def solve_unknown_arm(
    unknown_arm: str, known_arms: Mapping[str, float]
) -> tuple[float, str]:
    """由平衡条件反推待测臂的闭式解。

    返回 (阻值, 表达式文本)。输入合法性由 validation 模块保证，
    此处假定 known_arms 恰好含其余三臂且均为正有限值。
    """
    a, b, partner = _FORMULAS[unknown_arm]
    value = known_arms[a] * known_arms[b] / known_arms[partner]
    formula = f"{unknown_arm} = {a}*{b}/{partner}"
    return value, formula
