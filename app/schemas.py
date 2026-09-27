"""请求/响应模型（仅数据结构，不含计算逻辑）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class PresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arms: dict[str, float] = Field(description="四臂阻值，键为 r1..r4")
    description: str | None = None


class PresetResponse(BaseModel):
    name: str
    arms: dict[str, float]
    description: str | None
