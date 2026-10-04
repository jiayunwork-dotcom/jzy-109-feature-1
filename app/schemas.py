"""请求/响应模型（仅数据结构，不含计算逻辑）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: 电桥类型字面量
BridgeType = Literal["wheatstone", "kelvin"]


# --------------------------------------------------------------------------
# 四臂惠斯通电桥（字段与历史完全一致）
# --------------------------------------------------------------------------


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
    method: str = Field(
        default="closed_form",
        description="检流计量的求解路径：closed_form=闭式（对照），nodal=节点方程",
    )


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
    bridge_type: str = Field(default="wheatstone", description="电桥类型")
    nodal: "NodalCrossCheck | None" = Field(
        default=None,
        description="同一结果经通用节点方程底子的独立复算（与闭式的一致性被测试锁死）",
    )


class NodalCrossCheck(BaseModel):
    """闭式结果 vs 通用节点方程底子的逐项交叉核对。"""

    open_circuit_voltage: float = Field(description="节点方程给出的开路输出（伏）")
    output_relative_error: float = Field(description="开路输出与闭式的相对误差")
    galvanometer_current: float | None = Field(
        default=None, description="节点方程给出的检流计电流（安）"
    )
    galvanometer_relative_error: float | None = Field(
        default=None, description="检流计电流与闭式的相对误差（零电流时给绝对误差）"
    )
    thevenin_resistance: float = Field(description="节点方程给出的戴维南等效内阻（欧）")


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
    bridge_type: str = Field(default="wheatstone", description="电桥类型")


# --------------------------------------------------------------------------
# 电桥档
# --------------------------------------------------------------------------


class PresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arms: dict[str, float] | None = Field(
        default=None, description="四臂阻值（type=wheatstone 或不带类型时必填）"
    )
    description: str | None = None
    type: BridgeType | None = Field(
        default=None,
        description="电桥类型：wheatstone（缺省，老式登记按此处理）或 kelvin",
    )
    kelvin: dict[str, float] | None = Field(
        default=None, description="双电桥参数（type=kelvin 时必填）"
    )
    source_current: float | None = Field(
        default=None, description="双电桥恒流源电流（安，type=kelvin 时必填）"
    )


class PresetResponse(BaseModel):
    name: str
    type: str = Field(description="电桥类型：wheatstone / kelvin")
    arms: dict[str, float] | None = Field(default=None, description="四臂阻值（四臂档）")
    kelvin: dict[str, float] | None = Field(default=None, description="双电桥参数（双电桥档）")
    source_current: float | None = Field(default=None, description="恒流源电流（双电桥档）")
    description: str | None = None


# --------------------------------------------------------------------------
# 开尔文双电桥
# --------------------------------------------------------------------------


class KelvinForwardRequest(BaseModel):
    """双电桥正算：双电桥参数（或双电桥档）+ 恒流源电流，可选检流计内阻。"""

    model_config = ConfigDict(extra="forbid")

    kelvin: dict[str, float] | None = Field(
        default=None, description="双电桥参数；与 preset 二选一"
    )
    preset: str | None = Field(default=None, description="双电桥档名；与 kelvin 二选一")
    source_current: float = Field(description="恒流源电流（安）；零给出零输出；负值反向")
    galvanometer_resistance: float | None = Field(
        default=None, description="检流计内阻（欧）。不提供则只算开路输出"
    )


class KelvinSolveRequest(BaseModel):
    """双电桥反推：由平衡闭式反推待测电阻 rx，并代回节点正算自洽核查。"""

    model_config = ConfigDict(extra="forbid")

    kelvin: dict[str, float] | None = Field(
        default=None,
        description="双电桥参数（rs、r1..r4、yoke、接触电阻）；与 preset 二选一，rx 无需给",
    )
    preset: str | None = Field(default=None, description="双电桥档名；与 kelvin 二选一")
    source_current: float | None = Field(
        default=None,
        description="自洽核查用恒流源电流（安）；给档时可省，用档内电流",
    )


class KelvinForwardResponse(BaseModel):
    bridge_type: str = Field(default="kelvin")
    kelvin: dict[str, float] = Field(description="本次正算所用的完整双电桥参数（含 rx）")
    preset: str | None
    source_current: float
    node_voltage_m: float = Field(description="外臂汇合点 M 的电位（伏）")
    node_voltage_n: float = Field(description="内臂汇合点 N 的电位（伏）")
    output_voltage: float = Field(description="开路输出 V_M − V_N（伏）")
    thevenin_resistance: float = Field(description="M、N 端口的戴维南等效内阻（欧）")
    balanced: bool = Field(description="开路输出是否为零（容差 1e-9 相对标度）")
    zero_source: bool
    notes: list[str]
    galvanometer: GalvanometerResult | None


class KelvinSolveResponse(BaseModel):
    bridge_type: str = Field(default="kelvin")
    solved_resistance: float = Field(description="反推出的待测电阻 rx（欧）")
    main_term: float = Field(description="主比例项 (r1/r2)·rs（欧）")
    correction: float = Field(description="轭线修正项 Δ（欧）；内外比例一致时严格为零")
    formula: str = Field(description="所用闭式表达式")
    balance_condition: str
    kelvin: dict[str, float] = Field(description="含解出 rx 在内的完整双电桥参数")
    closure_source_current: float = Field(description="自洽核查用恒流源电流（安）")
    closure_output_voltage: float = Field(
        description="把解出的 rx 代回双电桥节点正算的开路输出（应为零）"
    )
    closure_galvanometer_current: float = Field(
        description="代回并接 50 Ω 检流计后的偏转电流（应为零）"
    )
