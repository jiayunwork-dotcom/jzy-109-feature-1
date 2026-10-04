r"""开尔文双电桥（Kelvin double bridge）的拓扑与编号约定。

低值电阻（毫欧级分流器、母排）是**四端器件**：两个电流端 C 走主回路大
电流，两个电位端 P 只取电位（比例臂支路电流极小）。这样引线与接触电阻
被各自赶到不影响测量的支路里——这正是双电桥相对四臂惠斯通电桥的意义。

拓扑图（本服务全代码、文档、接口统一以此为准）::

      S+ ──rc1── n1 ─────── R_x ─────── n2 ──rc2── y2
       │         (P1)                (P2)            │
      恒流源                                          轭线 r_y
      I_s                                            │
       │         (P3)                (P4)           y3 ──rc3── n3
      S- ──rc4── n4 ─────── R_s ─────────────────── n3

      外比例臂：n1(P1) ─rp1─R1─ M ─R2─rp3─ n4(P3)     （R1、R2 汇合成 M）
      内比例臂：n2(P2) ─rp2─R3─ N ─R4─rp4─ n3(P4)     （R3、R4 汇合成 N）
      检流计：    M ───────────── G ───────────── N   （正方向 M → N）

正确的汇合关系（内外臂不得接错，接错就不是双电桥）：

* **外比例臂** R1（P1 侧）与 R2（P3 侧）的另一端**汇合成同一点 M**；
* **内比例臂** R3（P2 侧）与 R4（P4 侧）的另一端**汇合成同一点 N**；
* **检流计 G 跨在 M、N 之间**，正方向取 M → N，开路输出 V_out = V_M − V_N。

即两条分压支路为：

    外支路（跨整段 R_x + 轭线 + R_s）：n1 ─R1─ M ─R2─ n4
    内支路（跨轭线段）：              n2 ─R3─ N ─R4─ n3

编号约定（不许含糊）：

- **n1**：R_x 外侧电流端 C1（朝恒流源 S+）；**n4**：R_s 外侧电流端 C4（朝 S-）。
- **n2**：R_x 内侧电流端 C2（朝轭线）；**n3**：R_s 内侧电流端 C3（朝轭线）。
- 主回路串联顺序：S+ → rc1 → n1(C1) →（P1 取点）→ **R_x** →（P2 取点）
  → n2(C2) → rc2 → **轭线 r_y** → rc3 → n3(C3) →（P4 取点）→ **R_s**
  →（P3 取点）→ n4(C4) → rc4 → S-。
- **电位端**：P1、P2 属 R_x（P1 在外、P2 在内）；P3、P4 属 R_s
  （P3 在外、P4 在内）。
- **主比例** = R1/R2（外臂），**内比例** = R3/R4；平衡条件 V_M = V_N。

接触电阻（每个电流端、每个电位端都允许单独填一个非负值，不填按零；
它们作为元件进入节点方程，绝不事后加减）：

- rc1：C1 电流端（恒流源—P1 之间）；rc4：C4 电流端（P3—恒流源）；
- rc2：C2 电流端（P2—轭线之间）；rc3：C3 电流端（轭线—P4 之间）；
- rp1：P1 电位端（串进 R1）；rp2：P2 电位端（串进 R3）；
- rp3：P3 电位端（串进 R2）；rp4：P4 电位端（串进 R4）。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 接触电阻字段名 → 物理含义（顺序即文档顺序）
CONTACT_FIELDS: tuple[str, ...] = ("rc1", "rc2", "rc3", "rc4", "rp1", "rp2", "rp3", "rp4")

#: 电流端接触 / 电位端接触分组
CURRENT_CONTACTS: tuple[str, ...] = ("rc1", "rc2", "rc3", "rc4")
POTENTIAL_CONTACTS: tuple[str, ...] = ("rp1", "rp2", "rp3", "rp4")


@dataclass(frozen=True)
class KelvinBridge:
    """一套双电桥参数（电阻单位欧，恒流源电流单位安）。

    反解时 rx 可由档带出或忽略；正算时必须给出。接触电阻不填即零。
    """

    rx: float
    rs: float
    r1: float
    r2: float
    r3: float
    r4: float
    yoke: float = 0.0
    rc1: float = 0.0
    rc2: float = 0.0
    rc3: float = 0.0
    rc4: float = 0.0
    rp1: float = 0.0
    rp2: float = 0.0
    rp3: float = 0.0
    rp4: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "rx": self.rx, "rs": self.rs,
            "r1": self.r1, "r2": self.r2, "r3": self.r3, "r4": self.r4,
            "yoke": self.yoke,
            "rc1": self.rc1, "rc2": self.rc2, "rc3": self.rc3, "rc4": self.rc4,
            "rp1": self.rp1, "rp2": self.rp2, "rp3": self.rp3, "rp4": self.rp4,
        }

    def contacts_dict(self) -> dict[str, float]:
        return {f: getattr(self, f) for f in CONTACT_FIELDS}


#: 双电桥平衡条件的规范文本，接口响应中回显
BALANCE_CONDITION = "V_M = V_N（外臂汇合点 M 与内臂汇合点 N 等电位）"
