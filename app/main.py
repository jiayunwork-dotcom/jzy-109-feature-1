"""HTTP 层：只负责收发请求与编排调用，电学计算全部在 app.bridge 各模块中。

两种电桥：
- 四臂惠斯通电桥：``/v1/bridge/*``，字段/错误码与历史版本完全一致；
  正算在闭式结果旁增加通用节点方程路径并逐项核对（相对误差 1e-9 内）。
- 开尔文双电桥：``/v1/kelvin/*`` 独立接口；正算只走通用节点方程，
  反推走平衡闭式解并代回节点正算闭合。

电桥档带 ``bridge_type``；老式无类型登记按 ``wheatstone`` 处理。
拿错类型档调接口返回 ``preset_type_mismatch``，不静默取错字段。
"""
from __future__ import annotations

from fastapi import FastAPI, Path, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app import validation
from app.bridge import balance as balance_mod
from app.bridge import forward, thevenin
from app.bridge import kelvin_balance, kelvin_forward, kelvin_validation, nodal
from app.bridge.topology import ARM_NAMES, ArmSet
from app.bridge.wheatstone_circuit import analyze as wheatstone_nodal_analyze
from app.presets import (
    DEFAULT_BRIDGE_TYPE,
    KELVIN,
    WHEATSTONE,
    Preset,
    PresetStore,
)
from app.schemas import (
    ForwardRequest,
    ForwardResponse,
    GalvanometerResult,
    KelvinConfigModel,
    KelvinForwardRequest,
    KelvinForwardResponse,
    KelvinGalvanometerResult,
    KelvinSolveRequest,
    KelvinSolveResponse,
    PresetRequest,
    PresetResponse,
    SolveRequest,
    SolveResponse,
)
from app.validation import BridgeInputError

APP_DESCRIPTION = """惠斯通电桥 / 开尔文双电桥核算服务（仅 HTTP 接口，无网页）。

四臂惠斯通电桥臂编号::

            A (桥源正端)
           / \\
         R1     R2
         /       \\
        B ───G─── D     B、D：输出端子；G：检流计（可选）
         \\       /
         R3     R4
           \\   /
            C (桥源负端，参考地)

开路输出 V_out = Vs·(R3/(R1+R3) − R4/(R2+R4))；
平衡条件为相对臂乘积相等：R1·R4 = R2·R3。

开尔文双电桥（毫欧级低值电阻，四端测量）编号与拓扑见 README；
j 为两外臂 R1/R2 汇合点，k 为两内臂 r3/r4 汇合点，检流计跨 j、k。
平衡式 Rx = (R1'/R2')·Rs + Ry'·(R1'·r4'−R2'·r3')/[R2'·(r3'+r4'+Ry')]。
"""

#: 四臂反解自洽核查用的探针桥源电压（伏）
_PROBE_VOLTAGE = 1.0
#: 双电桥自洽核查用的探针恒流源电流（安）
_PROBE_CURRENT = 1.0
#: 双电桥检流计自洽核查内阻（欧）
_PROBE_GALVANOMETER = 50.0
#: 两条正算路径（闭式 vs 节点方程）一致性容差
_NODAL_CROSSCHECK_TOL = 1e-9

app = FastAPI(title="电桥核算服务", version="2.0.0", description=APP_DESCRIPTION)

#: 电桥档登记处（进程内存，跨重启不保留）
store = PresetStore()

_STATUS_BY_CODE = {"preset_not_found": 404}


@app.exception_handler(BridgeInputError)
async def bridge_input_error_handler(_request: Request, exc: BridgeInputError) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_CODE.get(exc.code, 400),
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(nodal.NetworkError)
async def network_error_handler(_request: Request, exc: nodal.NetworkError) -> JSONResponse:
    """节点方程的奇异/病态错误：带原因返回，绝不透出线性代数异常或 NaN/Inf。"""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request_invalid",
                "message": "请求不符合接口约定（字段缺失或类型错误）",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


# ============================ 四臂惠斯通电桥 ============================


def _resolve_arms(raw_arms: dict | None, preset_name: str | None) -> tuple[ArmSet, str | None]:
    """arms 与 preset 二选一，解析出经校验的四臂集合；档类型不符明确报错。"""
    if raw_arms is not None and preset_name is not None:
        raise BridgeInputError("arms_source_ambiguous", "arms 与 preset 只能二选一")
    if preset_name is not None:
        preset = store.get(preset_name)
        if preset is None:
            raise BridgeInputError("preset_not_found", f"电桥档 {preset_name!r} 不存在")
        if preset.bridge_type != WHEATSTONE:
            raise BridgeInputError(
                "preset_type_mismatch",
                f"电桥档 {preset_name!r} 是开尔文双电桥档（kelvin），"
                "不能用于四臂惠斯通电桥接口；请改用 /v1/kelvin/* 接口",
            )
        return preset.arms, preset_name
    if raw_arms is None:
        raise BridgeInputError(
            "arms_source_missing", "必须提供 arms（四臂阻值）或 preset（电桥档名）之一"
        )
    return validation.require_arm_set(raw_arms), None


def _wheatstone_preset_response(preset: Preset) -> PresetResponse:
    return PresetResponse(
        name=preset.name,
        bridge_type=preset.bridge_type,
        arms=preset.arms.as_dict(),
        kelvin_config=None,
        description=preset.description,
    )


@app.get("/")
def root() -> dict:
    return {
        "service": "电桥核算服务",
        "version": "2.0.0",
        "bridge_types": ["wheatstone", "kelvin"],
        "balance_conditions": {
            "wheatstone": balance_mod.BALANCE_CONDITION,
            "kelvin": kelvin_balance.BALANCE_CONDITION,
        },
        "endpoints": {
            "wheatstone_output": "POST /v1/bridge/output",
            "wheatstone_solve": "POST /v1/bridge/solve",
            "kelvin_output": "POST /v1/kelvin/output",
            "kelvin_solve": "POST /v1/kelvin/solve",
            "presets": "PUT/GET/DELETE /v1/presets[/{name}]",
        },
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/v1/bridge/output", response_model=ForwardResponse)
def bridge_output(req: ForwardRequest) -> ForwardResponse:
    """正算：开路不平衡输出；给检流计内阻时附戴维南等效下的实际偏转量。

    闭式路径（forward/thevenin）保留为对外结果与对照；通用节点方程
    路径（nodal）并行计算并逐项核对，相对误差超过 1e-9 即内部报错，
    两条路径的一致性由自动化测试锁住。
    """
    arms, preset_name = _resolve_arms(req.arms, req.preset)
    vs = validation.validate_source_voltage(req.source_voltage)
    rg = validation.validate_galvanometer(req.galvanometer_resistance)

    # ---- 闭式路径（历史结果，字段与取值保持不变） ----
    v_b = forward.divider_voltage_b(arms, vs)
    v_d = forward.divider_voltage_d(arms, vs)
    v_out = v_b - v_d
    prod_left, prod_right = balance_mod.balance_products(arms)

    notes: list[str] = []
    zero_source = vs == 0.0
    if zero_source:
        notes.append("桥源电压为零：输出为零，属正常情形而非错误")

    galvanometer = None
    if rg is not None:
        current = thevenin.galvanometer_current(arms, vs, rg)
        galvanometer = GalvanometerResult(
            resistance=rg,
            thevenin_voltage=thevenin.thevenin_voltage(arms, vs),
            thevenin_resistance=thevenin.thevenin_resistance(arms),
            current=current,
            voltage=current * rg,
        )
        notes.append("检流计偏转量与电流成正比；电流由戴维南等效严格求得")

    # ---- 通用节点方程路径（两种电桥共用的底子）：与闭式逐项交叉核对 ----
    # 开路量（与检流计是否接入无关：先解开路网络）
    nodal_open = wheatstone_nodal_analyze(arms, vs, None)
    _crosscheck_close("B 点电位", v_b, nodal_open.v_b)
    _crosscheck_close("D 点电位", v_d, nodal_open.v_d)
    _crosscheck_close("开路输出", v_out, nodal_open.open_circuit_voltage)
    _crosscheck_close(
        "戴维南内阻",
        thevenin.thevenin_resistance(arms),
        nodal_open.thevenin_resistance,
    )
    if rg is not None:
        # 带载量：接检流计后 B/D 电位因取流偏离开路灯值，只核对检流计量
        nodal_loaded = wheatstone_nodal_analyze(arms, vs, rg)
        _crosscheck_close("检流计电流", galvanometer.current, nodal_loaded.galvanometer_current)
        _crosscheck_close("检流计电压", galvanometer.voltage, nodal_loaded.galvanometer_voltage)
    notes.append("正算已由通用节点方程独立复核，与闭式结果逐项吻合（容差 1e-9）")

    return ForwardResponse(
        arms=arms.as_dict(),
        preset=preset_name,
        source_voltage=vs,
        divider_voltage_b=v_b,
        divider_voltage_d=v_d,
        output_voltage=v_out,
        balanced=balance_mod.is_balanced(arms),
        balance_products={"r1*r4": prod_left, "r2*r3": prod_right},
        zero_source=zero_source,
        notes=notes,
        galvanometer=galvanometer,
    )


def _crosscheck_close(label: str, closed: float, nodal_value: float | None) -> None:
    """两条正算路径的结果必须相对吻合；真零值用绝对容差。"""
    if nodal_value is None:
        raise BridgeInputError(
            "internal_crosscheck_failed", f"节点方程路径缺少 {label} 结果"
        )
    scale = max(1.0, abs(closed), abs(nodal_value))
    if abs(closed - nodal_value) > _NODAL_CROSSCHECK_TOL * scale:
        raise BridgeInputError(
            "internal_crosscheck_failed",
            f"闭式结果与节点方程结果在 {label} 上不一致："
            f"{closed!r} vs {nodal_value!r}",
        )


@app.post("/v1/bridge/solve", response_model=SolveResponse)
def bridge_solve(req: SolveRequest) -> SolveResponse:
    """反解：由三个已知臂按平衡条件闭式解出待测臂，并代回正算做自洽核查。"""
    unknown = validation.validate_unknown_arm(req.unknown_arm)
    validation.validate_solve_target(req.target_output_voltage)

    if req.preset is not None and req.known_arms is not None:
        raise BridgeInputError("arms_source_ambiguous", "known_arms 与 preset 只能二选一")
    if req.preset is not None:
        preset = store.get(req.preset)
        if preset is None:
            raise BridgeInputError("preset_not_found", f"电桥档 {req.preset!r} 不存在")
        if preset.bridge_type != WHEATSTONE:
            raise BridgeInputError(
                "preset_type_mismatch",
                f"电桥档 {req.preset!r} 是开尔文双电桥档（kelvin），"
                "不能用于四臂惠斯通电桥反解接口；请改用 /v1/kelvin/solve",
            )
        known = {n: getattr(preset.arms, n) for n in ARM_NAMES if n != unknown}
    else:
        known = validation.validate_known_arms(unknown, req.known_arms)

    solved, formula = balance_mod.solve_unknown_arm(unknown, known)
    full = ArmSet(**{**known, unknown: solved})
    prod_left, prod_right = balance_mod.balance_products(full)
    closure = forward.open_circuit_output(full, _PROBE_VOLTAGE)

    return SolveResponse(
        unknown_arm=unknown,
        solved_resistance=solved,
        formula=formula,
        balance_condition=balance_mod.BALANCE_CONDITION,
        arms=full.as_dict(),
        balance_products={"r1*r4": prod_left, "r2*r3": prod_right},
        closure_probe_voltage=_PROBE_VOLTAGE,
        closure_output_voltage=closure,
    )


# ============================ 开尔文双电桥 ============================


def _kelvin_config_from_model(model: KelvinConfigModel):
    return kelvin_validation.build_config(
        ratio_arms=model.ratio_arms,
        standard_resistance=model.standard_resistance,
        yoke_resistance=model.yoke_resistance,
        contacts=model.contacts.model_dump() if model.contacts is not None else None,
    )


def _resolve_kelvin_config(
    config_model: KelvinConfigModel | None, preset_name: str | None
):
    """config 与 preset 二选一；取档时校验类型必须是 kelvin。"""
    if config_model is not None and preset_name is not None:
        raise BridgeInputError("arms_source_ambiguous", "config 与 preset 只能二选一")
    if preset_name is not None:
        preset = store.get(preset_name)
        if preset is None:
            raise BridgeInputError("preset_not_found", f"电桥档 {preset_name!r} 不存在")
        if preset.bridge_type != KELVIN:
            raise BridgeInputError(
                "preset_type_mismatch",
                f"电桥档 {preset_name!r} 是四臂惠斯通电桥档（wheatstone），"
                "不能用于开尔文双电桥接口；请改用 /v1/bridge/* 接口",
            )
        return preset.config, preset_name
    if config_model is None:
        raise BridgeInputError(
            "arms_source_missing", "必须提供 config（双电桥配置）或 preset（电桥档名）之一"
        )
    return _kelvin_config_from_model(config_model), None


def _kelvin_config_dict(config, preset_name: str | None) -> dict:
    return {
        "ratio_arms": config.ratio_arms(),
        "standard_resistance": config.Rs,
        "yoke_resistance": config.Ry,
        "contacts": config.contacts.as_dict(),
    }


@app.post("/v1/kelvin/output", response_model=KelvinForwardResponse)
def kelvin_output(req: KelvinForwardRequest) -> KelvinForwardResponse:
    """双电桥正算：开路输出（节点方程）；可选检流计偏转电流。"""
    config, preset_name = _resolve_kelvin_config(req.config, req.preset)
    rx = kelvin_validation.require_unknown_resistance(req.unknown_resistance)
    current_src = kelvin_validation.require_source_current(req.source_current)
    rg = validation.validate_galvanometer(req.galvanometer_resistance)

    result = kelvin_forward.analyze(config, rx, current_src, rg)

    notes: list[str] = []
    zero_source = current_src == 0.0
    if zero_source:
        notes.append("恒流源电流为零：输出为零，属正常情形而非错误")
    notes.append("开路输出、戴维南等效与检流计电流均由通用节点方程解出")

    galvanometer = None
    if rg is not None:
        galvanometer = KelvinGalvanometerResult(
            resistance=rg,
            thevenin_voltage=result.open_circuit_voltage,
            thevenin_resistance=result.thevenin_resistance,
            current=result.galvanometer_current,
            voltage=result.galvanometer_voltage,
        )

    return KelvinForwardResponse(
        preset=preset_name,
        config=_kelvin_config_dict(config, preset_name),
        unknown_resistance=rx,
        source_current=current_src,
        junction_voltage_out=result.v_p1,
        junction_voltage_in=result.v_p2,
        output_voltage=result.open_circuit_voltage,
        zero_source=zero_source,
        balanced=abs(result.open_circuit_voltage) <= 1e-12 * max(1.0, abs(current_src)),
        notes=notes,
        galvanometer=galvanometer,
    )


@app.post("/v1/kelvin/solve", response_model=KelvinSolveResponse)
def kelvin_solve(req: KelvinSolveRequest) -> KelvinSolveResponse:
    """双电桥反推：平衡闭式解反推 Rx，并代回节点正算核查零输出/零检流计电流。"""
    config, preset_name = _resolve_kelvin_config(req.config, req.preset)
    result = kelvin_balance.solve_rx(config)

    # 代回节点正算：开路输出必须为零
    closure_voltage = kelvin_forward.open_circuit_voltage(
        config, result.rx, _PROBE_CURRENT
    )
    # 接检流计后的偏转电流也必须为零
    closure_analysis = kelvin_forward.analyze(
        config, result.rx, _PROBE_CURRENT, _PROBE_GALVANOMETER
    )

    return KelvinSolveResponse(
        preset=preset_name,
        solved_resistance=result.rx,
        main_term=result.main_term,
        correction_term=result.correction_term,
        formula=kelvin_balance.FORMULA,
        balance_condition=kelvin_balance.BALANCE_CONDITION,
        config=_kelvin_config_dict(config, preset_name),
        effective_arms=result.effective.as_dict(),
        closure_source_current=_PROBE_CURRENT,
        closure_output_voltage=closure_voltage,
        closure_galvanometer_current=closure_analysis.galvanometer_current,
    )


# ============================ 电桥档 ============================


_PRESET_NAME = Path(
    pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    description="电桥档名：字母数字开头，可含 - 和 _，最长 64 字符",
)


def _kelvin_preset_response(preset: Preset) -> PresetResponse:
    cfg = preset.config
    return PresetResponse(
        name=preset.name,
        bridge_type=KELVIN,
        arms=None,
        kelvin_config={
            "ratio_arms": cfg.ratio_arms(),
            "standard_resistance": cfg.Rs,
            "yoke_resistance": cfg.Ry,
            "contacts": cfg.contacts.as_dict(),
        },
        description=preset.description,
    )


def _preset_response(preset: Preset) -> PresetResponse:
    if preset.bridge_type == KELVIN:
        return _kelvin_preset_response(preset)
    return _wheatstone_preset_response(preset)


@app.put("/v1/presets/{name}", response_model=PresetResponse)
def put_preset(req: PresetRequest, name: str = _PRESET_NAME) -> PresetResponse:
    """登记（或整体替换）一套电桥档；四臂档与双电桥档按 bridge_type 区分。

    老式不带 bridge_type 的请求按 wheatstone 处理，行为与改动前一致。
    """
    if req.bridge_type == KELVIN:
        if req.arms is not None:
            raise BridgeInputError(
                "preset_fields_type_conflict",
                "kelvin 档使用 kelvin_config，不能同时提供四臂 arms",
            )
        if req.kelvin_config is None:
            raise BridgeInputError(
                "kelvin_config_missing", "bridge_type 为 kelvin 时必须提供 kelvin_config"
            )
        config = _kelvin_config_from_model(req.kelvin_config)
        preset = Preset(
            name=name, config=config, bridge_type=KELVIN, description=req.description
        )
        return _preset_response(store.register(name, preset))

    # wheatstone（含老式无类型请求）
    if req.arms is None:
        raise BridgeInputError("arm_missing", "四臂电桥档必须提供 arms（r1..r4）")
    if req.kelvin_config is not None:
        raise BridgeInputError(
            "preset_fields_type_conflict",
            "wheatstone 档使用 arms，不能同时提供 kelvin_config",
        )
    arms = validation.require_arm_set(req.arms)
    preset = Preset(
        name=name, config=arms, bridge_type=DEFAULT_BRIDGE_TYPE, description=req.description
    )
    return _preset_response(store.register(name, preset))


@app.get("/v1/presets", response_model=list[PresetResponse])
def list_presets() -> list[PresetResponse]:
    return [_preset_response(p) for p in store.list()]


@app.get("/v1/presets/{name}", response_model=PresetResponse)
def get_preset(name: str = _PRESET_NAME) -> PresetResponse:
    preset = store.get(name)
    if preset is None:
        raise BridgeInputError("preset_not_found", f"电桥档 {name!r} 不存在")
    return _preset_response(preset)


@app.delete("/v1/presets/{name}", status_code=204)
def delete_preset(name: str = _PRESET_NAME) -> Response:
    if not store.delete(name):
        raise BridgeInputError("preset_not_found", f"电桥档 {name!r} 不存在")
    return Response(status_code=204)
