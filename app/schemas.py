"""请求/响应模型（仅数据结构，不含计算逻辑）。

四臂惠斯通电桥的既有字段全部保持原样（老调用方请求/响应不变）；
新增内容：电桥档的 ``bridge_type`` 标注，以及开尔文双电桥的两套
请求/响应模型（走独立接口路径）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: 电桥类型
BridgeType = Literal["wheatstone", "kelvin"]


# ============================ 四臂惠斯通电桥 ============================


class ForwardRequest(BaseModel):
    """不平衡输出请求：四臂阻值（或电桥档名）+ 桥源电压，可选检流计内阻。"""

    model_config = ConfigDict(extra="forbid")

    arms: dict[str, float] | None = Field(
        default=None, description="四臂阻值，键为 r1..r4；与 preset 二选一"
    )
    preset: str | None = Field(default=None, description="电桥档名；与 arms 二选一")
    source_voltage: float = Field(description="桥源电压（伏）。零给出零输出并标明；负值表示极性反接")
    galvanometer_resistance: float | None = Field(
        default=None, description="检流计内阻（欧）。不提供则只算开路输出"
    )


class GalvanometerResult(BaseModel):
    resistance: float = Field(description="检流计内阻 R_g（欧）")
    thevenin_voltage: float = Field(description="戴维南等效电压，即开路输出（伏）")
    thevenin_resistance: float = Field(description="戴维南等效内阻 (R1‖R3)+(R2‖R4)（欧）")
    current: float = Field(description="检流计电流 I_g = V_th/(R_th+R_g)（安），偏转量与之成正比")
    voltage: float = Field(description="检流计两端实际电压（伏）")


class ForwardResponse(BaseModel):
    arms: dict[str, float]
    preset: str | None
    source_voltage: float
    divider_voltage_b: float = Field(description="左支路 B 点电位（伏）")
    divider_voltage_d: float = Field(description="右支路 D 点电位（伏）")
    output_voltage: float = Field(description="开路输出 V_B − V_D（伏）")
    balanced: bool = Field(description="相对臂乘积是否相等（容差 1e-9）")
    balance_products: dict[str, float] = Field(description="两对相对臂乘积：r1*r4 与 r2*r3")
    zero_source: bool = Field(description="桥源电压为零：输出为零属正常情形")
    notes: list[str]
    galvanometer: GalvanometerResult | None


class SolveRequest(BaseModel):
    """反推待测臂请求：指定待求臂，给出其余三个已知臂（或取电桥档的其余三臂）。"""

    model_config = ConfigDict(extra="forbid")

    unknown_arm: str = Field(description="待求臂：r1、r2、r3、r4 之一")
    known_arms: dict[str, float] | None = Field(
        default=None, description="恰好三个已知臂；与 preset 二选一"
    )
    preset: str | None = Field(default=None, description="电桥档名：取该档其余三臂为已知")
    target_output_voltage: float | None = Field(
        default=None, description="目标输出电压；本接口只做平衡反推，若给出必须为 0"
    )


class SolveResponse(BaseModel):
    unknown_arm: str
    solved_resistance: float = Field(description="反推出的待测臂阻值（欧）")
    formula: str = Field(description="所用闭式表达式")
    balance_condition: str = Field(description="平衡条件：相对臂乘积相等")
    arms: dict[str, float] = Field(description="含解出臂在内的完整四臂")
    balance_products: dict[str, float]
    closure_probe_voltage: float = Field(description="自洽核查所用探针桥源电压（伏）")
    closure_output_voltage: float = Field(
        description="把解出的臂代回正算，在该探针电压下的输出（应为零）"
    )


# ============================ 开尔文双电桥 ============================


class KelvinContactsModel(BaseModel):
    """8 个端钮的接触电阻（欧，非负，不填按零），作为独立元件进入节点方程。"""

    model_config = ConfigDict(extra="forbid")

    rx_co_c: float = Field(default=0.0, description="待测电阻·外侧电流端接触电阻")
    rx_ci_c: float = Field(default=0.0, description="待测电阻·内侧电流端接触电阻")
    rx_po_c: float = Field(default=0.0, description="待测电阻·外侧电位端接触电阻（串入 R1 支路）")
    rx_pi_c: float = Field(default=0.0, description="待测电阻·内侧电位端接触电阻（串入 r3 支路）")
    rs_co_c: float = Field(default=0.0, description="标准电阻·外侧电流端接触电阻")
    rs_ci_c: float = Field(default=0.0, description="标准电阻·内侧电流端接触电阻")
    rs_po_c: float = Field(default=0.0, description="标准电阻·外侧电位端接触电阻（串入 R2 支路）")
    rs_pi_c: float = Field(default=0.0, description="标准电阻·内侧电位端接触电阻（串入 r4 支路）")


class KelvinConfigModel(BaseModel):
    """双电桥固定参数：四比例臂、标准电阻、轭线电阻、8 个端钮接触电阻。"""

    model_config = ConfigDict(extra="forbid")

    ratio_arms: dict[str, float] = Field(
        description="四只比例臂：R1、R2（外）、r3、r4（内）"
    )
    standard_resistance: float = Field(description="标准低值电阻 Rs（欧），必须为正")
    yoke_resistance: float = Field(
        default=0.0, description="轭线（两内侧电流端之间）电阻 Ry（欧），非负"
    )
    contacts: KelvinContactsModel | None = Field(
        default=None, description="8 个端钮接触电阻；不填按 0"
    )


class KelvinForwardRequest(BaseModel):
    """双电桥正算：固定配置（或电桥档名）+ 待测电阻 + 恒流源电流。"""

    model_config = ConfigDict(extra="forbid")

    config: KelvinConfigModel | None = Field(default=None, description="双电桥配置；与 preset 二选一")
    preset: str | None = Field(default=None, description="kelvin 类型电桥档名；与 config 二选一")
    unknown_resistance: float = Field(description="待测低值电阻 Rx（欧），必须为正")
    source_current: float = Field(
        description="恒流源电流（安）。零给出零输出（正常）；负值表示电流反向"
    )
    galvanometer_resistance: float | None = Field(
        default=None, description="检流计内阻（欧）；不提供则只算开路输出"
    )


class KelvinGalvanometerResult(BaseModel):
    resistance: float
    thevenin_voltage: float = Field(description="j、k 间开路输出电压（伏）")
    thevenin_resistance: float = Field(description="从 j、k 看进去的戴维南等效内阻（欧）")
    current: float = Field(description="检流计电流（安），偏转量与之成正比")
    voltage: float = Field(description="检流计两端实际电压（伏）")


class KelvinForwardResponse(BaseModel):
    bridge_type: Literal["kelvin"] = Field(default="kelvin")
    preset: str | None
    config: dict = Field(description="回显的固定配置（含接触电阻）")
    unknown_resistance: float
    source_current: float
    junction_voltage_out: float = Field(description="外臂汇合点 j 的对地电位（伏）")
    junction_voltage_in: float = Field(description="内臂汇合点 k 的对地电位（伏）")
    output_voltage: float = Field(description="开路输出 V_j − V_k（伏）")
    zero_source: bool = Field(description="恒流源电流为零：输出为零属正常情形")
    balanced: bool = Field(description="开路输出是否在容差内为零")
    notes: list[str]
    galvanometer: KelvinGalvanometerResult | None


class KelvinSolveRequest(BaseModel):
    """双电桥反推：按平衡闭式解反推待测低值电阻 Rx。"""

    model_config = ConfigDict(extra="forbid")

    config: KelvinConfigModel | None = Field(default=None, description="双电桥配置；与 preset 二选一")
    preset: str | None = Field(default=None, description="kelvin 类型电桥档名；与 config 二选一")


class KelvinSolveResponse(BaseModel):
    bridge_type: Literal["kelvin"] = Field(default="kelvin")
    preset: str | None
    solved_resistance: float = Field(description="反推出的待测电阻 Rx（欧）")
    main_term: float = Field(description="主比例项 (R1'/R2')·Rs（欧）")
    correction_term: float = Field(
        description="轭线修正项（欧）；内外比例一致时严格为零，随轭线电阻增大而增大"
    )
    formula: str
    balance_condition: str
    config: dict = Field(description="回显的固定配置（含接触电阻）")
    effective_arms: dict[str, float] = Field(
        description="计入接触电阻后的有效臂与有效轭线电阻"
    )
    closure_source_current: float = Field(description="自洽核查所用探针恒流源电流（安）")
    closure_output_voltage: float = Field(
        description="把解出的 Rx 代回双电桥节点正算，开路输出（应为零）"
    )
    closure_galvanometer_current: float = Field(
        description="把解出的 Rx 代回并接检流计后的偏转电流（应为零）"
    )


# ============================ 电桥档 ============================


class PresetRequest(BaseModel):
    """登记电桥档。

    ``bridge_type`` 缺省为 ``wheatstone``：老式不带类型的登记请求
    原样按四臂惠斯通电桥处理。四臂档给 ``arms``；双电桥档给
    ``kelvin_config`` 且 ``bridge_type`` 必须为 ``kelvin``。
    """

    model_config = ConfigDict(extra="forbid")

    bridge_type: BridgeType = Field(default="wheatstone")
    arms: dict[str, float] | None = Field(default=None, description="四臂阻值（wheatstone 档）")
    kelvin_config: KelvinConfigModel | None = Field(
        default=None, description="双电桥配置（kelvin 档）"
    )
    description: str | None = None


class PresetResponse(BaseModel):
    name: str
    bridge_type: BridgeType = Field(description="该档的电桥类型")
    arms: dict[str, float] | None = Field(
        default=None, description="四臂阻值；仅 wheatstone 档返回"
    )
    kelvin_config: dict | None = Field(
        default=None, description="双电桥配置；仅 kelvin 档返回"
    )
    description: str | None
