r"""桥臂编号约定（全服务统一，文档与接口均以此为准）。

电桥拓扑与臂编号::

                A (桥源正端)
               / \
              /   \
            R1     R2
            /       \
           B ───G─── D      B、D：输出端子；G：检流计（可选接入）
            \       /
            R3     R4
              \   /
               \ /
                C (桥源负端，参考地)

左分压支路：A → R1 → B → R3 → C，故 V_B = Vs · R3/(R1+R3)
右分压支路：A → R2 → D → R4 → C，故 V_D = Vs · R4/(R2+R4)

开路输出：V_out = V_B − V_D（正值表示 B 点电位高于 D 点）。

平衡条件：相对臂（对角臂）乘积相等，即 R1·R4 = R2·R3。
相对臂对为 (R1, R4) 与 (R2, R3)——是对角关系，不是相邻臂。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 四个桥臂的规范名（顺序即编号）
ARM_NAMES: tuple[str, ...] = ("r1", "r2", "r3", "r4")

#: 相对（对角）臂对：平衡条件为两对各自乘积相等
DIAGONAL_PAIRS: tuple[tuple[str, str], ...] = (("r1", "r4"), ("r2", "r3"))


@dataclass(frozen=True)
class ArmSet:
    """一套四臂阻值（欧姆）。不可变，电桥档之间因此天然互不影响。"""

    r1: float
    r2: float
    r3: float
    r4: float

    def as_dict(self) -> dict[str, float]:
        return {"r1": self.r1, "r2": self.r2, "r3": self.r3, "r4": self.r4}
