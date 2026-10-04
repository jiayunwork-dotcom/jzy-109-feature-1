r"""开尔文双电桥的平衡闭式反推（仅反解一侧使用；正算走节点方程）。

精确闭式推导（编号约定见 :mod:`app.bridge.kelvin_topology`）
===========================================================

无接触电阻时，主回路自恒流源高端起为

    n1 ── R_x ── n2 ── r_y（轭线）── n3 ── R_s ── n4

n4 取参考地，恒流源向 n1 注入电流 J（源端经 rc1 与 n1 相连，rc1 只在源
支路、不出现在下面的平衡关系里）。外臂 R1(n1→M)、R2(M→n4) 在外汇合点 M
分压；内臂 R3(n2→N)、R4(N→n3) 在内汇合点 N 分压。

由外臂（支路中无电源，电流连续）直接得

    V_M = V_1·R2/(R1 + R2)                                   …(1)

内臂支路 n2→R3→N→R4→n3 上电流连续：

    V_N = ( V_2·R4 + V_3·R3 ) / (R3 + R4)                    …(2)

平衡 V_M = V_N。再列三个主回路节点的 KCL（记 g_k = 1/R_k）：

  n1：J = (V_1−V_2)/R_x + (V_1−V_M)/R1
  n2：(V_1−V_2)/R_x = (V_2−V_3)/r_y + (V_2−V_N)/R3
  n3：(V_2−V_3)/r_y + (V_N−V_3)/R4 = V_3/R_s

将 (1)(2) 代入并逐式消元：由 n3 解出 V_3 = β·V_2（β 是仅含 R3,R4,R_s,r_y
的正系数），再由 n1、n2 消去 V_1、J，代入平衡条件，整理得到关于 R_x 的
线性方程，其解为

        R_x = (R1/R2)·R_s
              + r_y·(R1·R4 − R2·R3) / [ R2·(R3 + R4 + r_y) ]

记主比例 p = R1/R2、内比例 q = R3/R4，修正项可写成

        Δ = r_y·(p − q)·R4/(R3 + R4 + r_y)
          = r_y·(p − q) / (1 + (R3 + r_y)/R4)

性质（对应判据测试，已由节点方程逐项验证到机器精度）：

* **p = q（内外比例一致）时 Δ ≡ 0**，与轭线电阻无关：把 r_y 从 0 调到远
  大于 R_x，反推值严格等于 p·R_s；
* p ≠ q 时 Δ 随 r_y 单调变化（∂Δ/∂r_y 与 (p−q) 同号），r_y = 0 时 Δ = 0；
  对毫欧级轭线（r_y ≪ R3+R4，比例臂通常为百欧量级）Δ ≈ r_y·(p−q)·
  R4/(R3+R4)，这正是实验上要求内外比例严格配平的原因。

接触电阻（四端器件的关键，全部作为元件进入节点方程）
=====================================================

把各接触电阻并入它实际串入的元件后，闭式照原样成立：

* 电位端接触直接串进对应比例臂：
  R1 → R1+rp1，R2 → R2+rp3，R3 → R3+rp2，R4 → R4+rp4；
* 内侧电流端接触 rc2、rc3 与轭线串联：r_y → r_y + rc2 + rc3；
* **外侧电流端接触 rc1、rc4 在恒流源支路**：恒流源电流不变，它们只改变
  源端对地的整体电位，不改变任一比例臂分压比，故在 p = q（乃至任意比例）
  下都不移动平衡点。

这些闭式只用于反解接口；正算（开路输出、戴维南等效、检流计电流）一律解
整张电路的节点方程，见 :mod:`app.circuit.analysis`。
"""
from __future__ import annotations

from app.bridge.kelvin_topology import KelvinBridge

#: 反解闭式表达式文本
FORMULA = (
    "rx = (r1/r2)*rs"
    " + (yoke+rc2+rc3)*((r1+rp1)*(r4+rp4) - (r2+rp3)*(r3+rp2))"
    "/((r2+rp3)*((r3+rp2)+(r4+rp4)+(yoke+rc2+rc3)))"
)


def effective_parameters(bridge: KelvinBridge) -> dict[str, float]:
    """接触电阻并入对应元件后的等效 (R1, R2, R3, R4, r_y)。"""
    return {
        "r1": bridge.r1 + bridge.rp1,
        "r2": bridge.r2 + bridge.rp3,
        "r3": bridge.r3 + bridge.rp2,
        "r4": bridge.r4 + bridge.rp4,
        "yoke": bridge.yoke + bridge.rc2 + bridge.rc3,
    }


def solve_unknown_rx(bridge: KelvinBridge) -> tuple[float, float, float]:
    """按平衡闭式反推待测电阻。

    返回 (rx, main_term, correction)：主比例项 p·R_s 与轭线修正项 Δ。
    输入合法性（比例臂/标准电阻为正、接触非负、恒流源电流有限）由
    validation 层保证；闭式本身不依赖电流值。
    """
    eff = effective_parameters(bridge)
    r1, r2, r3, r4, yoke = eff["r1"], eff["r2"], eff["r3"], eff["r4"], eff["yoke"]

    main_term = (r1 / r2) * bridge.rs
    correction = yoke * (r1 * r4 - r2 * r3) / (r2 * (r3 + r4 + yoke))
    return main_term + correction, main_term, correction
