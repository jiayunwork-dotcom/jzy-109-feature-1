r"""开尔文双电桥平衡条件与待测电阻反推（闭式解）。

编号与接线见 :mod:`app.bridge.kelvin_topology`：j 是两只外臂 R1/R2 的
汇合点，k 是两只内臂 r3/r4 的汇合点，检流计跨 j、k；主回路沿
X_CO→Rx→X_CI→轭线 Ry→S_CI→Rs→S_CO。

闭式推导（网孔法，平衡即检流计零电流 Vj = Vk）
------------------------------------------------
记主回路电流为 I（X_CO→…→S_CO），内臂支路 k→… 的电流为 i（方向
k→r3→X_CI，即由 k 流入待测内侧）。平衡时 j、k 间无电流。

沿轭线/内臂节点 X_CI、S_CI 列 KCL：轭线电流为 I − i（在内侧节点分出
i 给内臂支路）。由 Vj = Vk 及四个比例臂上的压降，消去 I、i 两个中间
电流，得到标准开尔文平衡式

    Rx = (R1/R2)·Rs
         + Ry·(R1·r4 − R2·r3) / [ R2·(r3 + r4 + Ry) ]

两项的物理含义：

1. **主比例项** (R1/R2)·Rs：与四臂电桥同形，是外臂比例对标准电阻的换算。
2. **轭线修正项**：正比于轭线电阻 Ry，随 Ry 增大而增大；正比于内外臂
   的比例之差 (R1·r4 − R2·r3)——内外比例一致（R1/R2 = r3/r4，即
   R1·r4 = R2·r3）时修正项**严格为零**，此时把 Ry 从 0 调到远大于 Rx，
   反推值完全不变。

计入接触电阻后的有效臂（仅闭式反推侧做代数归并；正算侧接触电阻
始终是节点方程里的独立元件）：

    R1' = R1 + rx_po_c        R2' = R2 + rs_po_c     （电位端接触电阻串入外臂）
    r3' = r3 + rx_pi_c        r4' = r4 + rs_pi_c     （电位端接触电阻串入内臂）
    Ry' = Ry + rx_ci_c + rs_ci_c                      （内侧电流端接触电阻并入轭线）
    rx_co_c、rs_co_c 不进入公式：它们在主回路电流端，只改变恒流源两端
    承担的电压，不改变任何取压点电位（四端测量的核心价值）。

最终反推式：

    Rx = (R1'/R2')·Rs
         + Ry'·(R1'·r4' − R2'·r3') / [ R2'·(r3' + r4' + Ry') ]

正算一侧不用本闭式解，而由 :mod:`app.bridge.kelvin_forward` 解整张
电路的节点方程；反推值代回正算必须得到零检流计电流（自洽闭合测试）。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.bridge.kelvin_topology import KelvinConfig

#: 平衡条件的规范文本，接口响应中回显
BALANCE_CONDITION = (
    "Rx = (R1'/R2')·Rs + Ry'·(R1'·r4' − R2'·r3')/[R2'·(r3'+r4'+Ry')]，"
    "R1'=R1+rx_po_c、R2'=R2+rs_po_c、r3'=r3+rx_pi_c、r4'=r4+rs_pi_c、"
    "Ry'=Ry+rx_ci_c+rs_ci_c；内外比例一致时修正项严格为零"
)

#: 反推所用闭式表达式文本
FORMULA = (
    "Rx = (R1_eff/R2_eff)*Rs "
    "+ yoke_eff*(R1_eff*r4_eff - R2_eff*r3_eff)"
    "/(R2_eff*(r3_eff+r4_eff+yoke_eff))"
)


@dataclass(frozen=True)
class EffectiveArms:
    """计入接触电阻后的有效臂与有效轭线电阻（欧姆）。"""

    R1_eff: float
    R2_eff: float
    r3_eff: float
    r4_eff: float
    yoke_eff: float

    def as_dict(self) -> dict[str, float]:
        return {
            "R1_eff": self.R1_eff,
            "R2_eff": self.R2_eff,
            "r3_eff": self.r3_eff,
            "r4_eff": self.r4_eff,
            "yoke_eff": self.yoke_eff,
        }


def effective_arms(config: KelvinConfig) -> EffectiveArms:
    """按接触电阻串入的位置归并出有效臂/有效轭线（仅闭式反推侧使用）。"""
    c = config.contacts
    return EffectiveArms(
        R1_eff=config.R1 + c.rx_po_c,
        R2_eff=config.R2 + c.rs_po_c,
        r3_eff=config.r3 + c.rx_pi_c,
        r4_eff=config.r4 + c.rs_pi_c,
        yoke_eff=config.Ry + c.rx_ci_c + c.rs_ci_c,
    )


@dataclass(frozen=True)
class KelvinSolveResult:
    """反推结果：待测值、主比例项、轭线修正项与有效臂。"""

    rx: float
    main_term: float
    correction_term: float
    effective: EffectiveArms


def solve_rx(config: KelvinConfig) -> KelvinSolveResult:
    """由双电桥平衡条件闭式反推待测电阻 Rx。

    输入合法性（比例臂/标准电阻为正、轭线与接触电阻非负、电流有限）
    由 validation 模块在调用前保证。
    """
    eff = effective_arms(config)
    main_term = (eff.R1_eff / eff.R2_eff) * config.Rs

    # 轭线修正项：正比于轭线电阻与内外臂比例之差；比例一致时严格为零
    ratio_mismatch = eff.R1_eff * eff.r4_eff - eff.R2_eff * eff.r3_eff
    correction = (
        eff.yoke_eff * ratio_mismatch
        / (eff.R2_eff * (eff.r3_eff + eff.r4_eff + eff.yoke_eff))
    )
    return KelvinSolveResult(
        rx=main_term + correction,
        main_term=main_term,
        correction_term=correction,
        effective=eff,
    )
