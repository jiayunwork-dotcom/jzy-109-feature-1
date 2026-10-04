r"""开尔文双电桥（凯尔文双臂电桥）的拓扑、编号约定与网络构造。

毫欧级低值电阻（分流器、母排）必须四端测量：电流端走主回路大电流，
电位端只取压降、几乎无电流，引线/接触电阻不再与被测电阻同量级地
混入结果。编号约定全服务统一，README 中的拓扑图与本模块一致。

拓扑（理想元件级）::

              恒流源 I_s
          SRC+ ───────► GND
            │            ▲
        rx_co_c          │ rs_co_c        （外侧电流端接触电阻）
            ▼            │
          X_CO ──Rx── X_CI
            │            │
          X_PO          X_PI              （理想取压点，与同端电流端短接等电位）
            │            │
         rx_po_c       rx_pi_c            （电位端接触电阻）
            │            │
           R1           r3                （外/内比例臂，待测侧）
            │            │
            └────► j ◄───┘
                   │
                   G（检流计，可选，开路时不接入）
                   │
            ┌────► k ◄───┐
            │            │
           R2           r4                （外/内比例臂，标准侧）
            │            │
         rs_po_c       rs_pi_c
            │            │
          S_PO          S_PI
            │            │
          S_CO ──Rs── S_CI
            ▲            ▲
        rs_co_c      rs_ci_c
            │            │
           GND       yoke_s ◄──Ry── yoke_x
                                     │
                                 rx_ci_c（接 X_CI）   轭线串在两内侧电流端之间

主回路电流方向：SRC+ → X_CO → Rx → X_CI →（rx_ci_c）→ Ry
→（rs_ci_c）→ S_CI → Rs → S_CO →（rs_co_c）→ GND。

关键：检流计两侧 j、k 中，j 是两只**外**臂 R1/R2 的汇合点，
k 是两只**内**臂 r3/r4 的汇合点——R1 接待测外侧、R2 接标准外侧，
r3 接待测内侧、r4 接标准内侧。不能把外臂与内臂挂到检流计同一侧。

文字编号（权威定义，网络构造严格按此连接）
------------------------------------------------
主回路（大电流）：恒流源 → X_CO →〔Rx〕→ X_CI →〔轭线 Ry〕→ S_CI
→〔Rs〕→ S_CO → 恒流源。四个主节点沿主回路依次为

    X_CO  待测电阻 Rx 的**外侧**电流端（朝电源侧）
    X_CI  待测电阻 Rx 的**内侧**电流端（朝轭线侧）
    S_CI  标准电阻 Rs 的**内侧**电流端（朝轭线侧）
    S_CO  标准电阻 Rs 的**外侧**电流端（朝电源回流侧）

比例臂与检流计（电压测量回路）：

    R1 外比例臂：X_CO ──R1── j
    R2 外比例臂：S_CO ──R2── j     （两只外臂在 j 汇合）
    r3 内比例臂：X_CI ──r3── k
    r4 内比例臂：S_CI ──r4── k     （两只内臂在 k 汇合）
    检流计 G：跨接 j ──G── k（开路时不接入）

即检流计两侧分别是「两外臂汇合点 j」和「两内臂汇合点 k」——这是
"双臂"的含义，绝不能把外臂与内臂挂到检流计同一侧。

四个电位端 X_PO/X_PI/S_PO/S_PI 是从电阻体对应端头取出的理想取压点，
与同端的电流端钮等电位（见下短接线）；电位端钮面到比例臂之间串有
各自的接触电阻。

接触电阻（8 个，每个电流端/电位端独立，非负，不填按零）
------------------------------------------------
待测电阻四端：rx_co_c / rx_ci_c / rx_po_c / rx_pi_c
标准电阻四端：rs_co_c / rs_ci_c / rs_po_c / rs_pi_c

电流端接触电阻串在主回路里（外侧两只位于主回路电流端钮，内侧两只
与轭线串联）；电位端接触电阻串在对应比例臂支路里。它们一律作为
**独立元件进入节点方程**，不是在结果上事后加减。闭式反推侧按其
物理串入位置做代数归并（见 kelvin_balance.effective_arms）。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

# ---- 主节点名（沿主回路，与文字编号一一对应） ----
X_CO, X_CI, S_CI, S_CO = "X_CO", "X_CI", "S_CI", "S_CO"
# ---- 四个理想取压点（与同端电流端等电位） ----
X_PO, X_PI, S_PO, S_PI = "X_PO", "X_PI", "S_PO", "S_PI"
# ---- 检流计两侧：外臂汇合点 j、内臂汇合点 k ----
P_OUT, P_IN = "j", "k"
#: 兼容通用别名（正算模块用 P1/P2 语义）
P1, P2 = P_OUT, P_IN
# ---- 源与地 ----
SRC_POS = "SRC+"
GROUND = "GND"

#: 四个比例臂的规范名（外 R1/R2，内 r3/r4）
RATIO_NAMES: tuple[str, ...] = ("R1", "R2", "r3", "r4")

#: 8 个接触电阻的规范名
CONTACT_NAMES: tuple[str, ...] = (
    "rx_co_c", "rx_ci_c", "rx_po_c", "rx_pi_c",
    "rs_co_c", "rs_ci_c", "rs_po_c", "rs_pi_c",
)


@dataclass(frozen=True)
class KelvinContacts:
    """8 个端钮的接触电阻（欧姆，非负，缺省为 0）。"""

    rx_co_c: float = 0.0   # 待测·外侧电流端
    rx_ci_c: float = 0.0   # 待测·内侧电流端
    rx_po_c: float = 0.0   # 待测·外侧电位端（串入 R1 支路）
    rx_pi_c: float = 0.0   # 待测·内侧电位端（串入 r3 支路）
    rs_co_c: float = 0.0   # 标准·外侧电流端
    rs_ci_c: float = 0.0   # 标准·内侧电流端
    rs_po_c: float = 0.0   # 标准·外侧电位端（串入 R2 支路）
    rs_pi_c: float = 0.0   # 标准·内侧电位端（串入 r4 支路）

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in CONTACT_NAMES}


@dataclass(frozen=True)
class KelvinConfig:
    """双电桥固定参数：四只比例臂、标准电阻、轭线电阻与各端接触电阻。

    待测电阻 Rx 不放在配置里——由反推接口解出，或由正算接口另外给。
    """

    R1: float
    R2: float
    r3: float
    r4: float
    Rs: float
    Ry: float
    contacts: KelvinContacts = field(default_factory=KelvinContacts)

    def ratio_arms(self) -> dict[str, float]:
        return {"R1": self.R1, "R2": self.R2, "r3": self.r3, "r4": self.r4}


def build_network(
    config: KelvinConfig,
    rx: float,
    source_current: float,
    galvanometer_resistance: float | None = None,
):
    """把双电桥翻成通用电阻网络（接触电阻全部作为独立元件串入）。

    恒流源为 (SRC+, GROUND) 上的理想电流源，经外侧电流端接触电阻
    把主回路馈在 X_CO 与 S_CO 之间。
    """
    from app.bridge.nodal import ResistiveNetwork

    c = config.contacts
    resistors: list[tuple[str, str, float]] = []

    # ---- 主回路：源 → 外侧电流端接触电阻 → Rx → 内侧接触电阻 → 轭线
    #              → 内侧接触电阻 → Rs → 外侧接触电阻 → 地 ----
    resistors.append((SRC_POS, X_CO, c.rx_co_c))
    resistors.append((X_CO, X_CI, rx))
    resistors.append((X_CI, "yoke_x", c.rx_ci_c))
    resistors.append(("yoke_x", "yoke_s", config.Ry))
    resistors.append(("yoke_s", S_CI, c.rs_ci_c))
    resistors.append((S_CI, S_CO, config.Rs))
    resistors.append((S_CO, GROUND, c.rs_co_c))

    # ---- 外比例臂：取压点 → 电位端接触电阻 → 比例臂 → 外臂汇合点 j ----
    resistors.append((X_PO, "t_rx_po", c.rx_po_c))
    resistors.append(("t_rx_po", P_OUT, config.R1))
    resistors.append((S_PO, "t_rs_po", c.rs_po_c))
    resistors.append(("t_rs_po", P_OUT, config.R2))

    # ---- 内比例臂：取压点 → 电位端接触电阻 → 比例臂 → 内臂汇合点 k ----
    resistors.append((X_PI, "t_rx_pi", c.rx_pi_c))
    resistors.append(("t_rx_pi", P_IN, config.r3))
    resistors.append((S_PI, "t_rs_pi", c.rs_pi_c))
    resistors.append(("t_rs_pi", P_IN, config.r4))

    # ---- 电位端取压点与电阻体同端头等电位（理想四端取压短接线） ----
    resistors.append((X_PO, X_CO, 0.0))
    resistors.append((X_PI, X_CI, 0.0))
    resistors.append((S_PO, S_CO, 0.0))
    resistors.append((S_PI, S_CI, 0.0))

    # ---- 检流计（开路时不接入） ----
    if galvanometer_resistance is not None:
        resistors.append((P_OUT, P_IN, galvanometer_resistance))

    return ResistiveNetwork(
        resistors=tuple(resistors),
        current_sources=((SRC_POS, GROUND, source_current),),
        fixed_voltages={GROUND: 0.0},
    )


def passive_resistors(
    config: KelvinConfig, rx: float
) -> Sequence[tuple[str, str, float]]:
    """独立源置零（恒流源开路：移除含 SRC+ 的源支路）后的无源电阻表。"""
    return tuple(
        (a, b, r)
        for a, b, r in build_network(config, rx, 0.0).resistors
        if SRC_POS not in (a, b)
    )
