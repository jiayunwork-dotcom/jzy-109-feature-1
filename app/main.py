"""HTTP 层：只负责收发请求与编排调用，电学计算全部在 app.bridge 各模块中。"""
from __future__ import annotations

from fastapi import FastAPI, Path, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import validation
from app.bridge import balance as balance_mod
from app.bridge import forward, kelvin_balance, kelvin_forward, thevenin, wheatstone_nodal
from app.bridge.kelvin_topology import KelvinBridge
from app.bridge.topology import ARM_NAMES, ArmSet
from app.circuit.solver import NetworkEquationError
from app.presets import KELVIN, WHEATSTONE, Preset, PresetStore
from app.schemas import (
    ForwardRequest,
    ForwardResponse,
    GalvanometerResult,
    KelvinForwardRequest,
    KelvinForwardResponse,
    KelvinSolveRequest,
    KelvinSolveResponse,
    NodalCrossCheck,
    PresetRequest,
    PresetResponse,
    SolveRequest,
    SolveResponse,
)
from app.validation import BridgeInputError

APP_DESCRIPTION = """电阻电桥核算服务（仅 HTTP 接口，无网页）。

支持两种电桥：

* ``wheatstone`` 四臂惠斯通电桥：开路输出 V_out = Vs·(R3/(R1+R3) − R4/(R2+R4))，
  平衡条件 R1·R4 = R2·R3；
* ``kelvin`` 开尔文双电桥（毫欧级分流器/母排四端测量）：外臂 R1、R2 汇合于
  M，内臂 R3、R4 汇合于 N，检流计跨 M—N；平衡时
  R_x = (R1/R2)·R_s + r_y·(R1·R4−R2·R3)/(R2·(R3+R4+r_y))。

两种电桥的正算（开路输出、戴维南等效、检流计电流）统一解整张电路的节点
方程；四臂闭式保留作对照，双电桥闭式仅用于反解。
"""

#: 反解自洽核查用的探针激励
_PROBE_VOLTAGE = 1.0
_PROBE_CURRENT = 1.0
#: 自洽核查用检流计内阻（欧）
_CLOSURE_RG = 50.0
#: 闭式 vs 节点路径一致性锁定容差
NODAL_MATCH_REL_TOL = 1e-9

app = FastAPI(title="电阻电桥核算服务", version="2.0.0", description=APP_DESCRIPTION)

#: 电桥档登记处（进程内存，跨重启不保留）
store = PresetStore()

_STATUS_BY_CODE = {"preset_not_found": 404}


@app.exception_handler(BridgeInputError)
async def bridge_input_error_handler(_request: Request, exc: BridgeInputError) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_CODE.get(exc.code, 400),
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(NetworkEquationError)
async def network_equation_error_handler(_request: Request, exc: NetworkEquationError) -> JSONResponse:
    # 绝不把线性代数异常/无穷大/NaN 透出：转成带原因的 422
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
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


# --------------------------------------------------------------------------
# 电桥档解析（带类型把关）
# --------------------------------------------------------------------------


def _require_preset_type(preset: Preset, expected: str, interface: str) -> None:
    if preset.type != expected:
        other = "开尔文双电桥（kelvin）" if preset.type == KELVIN else "四臂惠斯通电桥（wheatstone）"
        raise BridgeInputError(
            "preset_type_mismatch",
            f"电桥档 {preset.name!r} 的类型是 {preset.type}（{other}），"
            f"不能用于{interface}；请改用对应类型的接口或电桥档",
        )


def _resolve_arms(raw_arms: dict | None, preset_name: str | None) -> tuple[ArmSet, str | None]:
    """arms 与 preset 二选一，解析出经校验且类型为四臂的四臂集合。"""
    if raw_arms is not None and preset_name is not None:
        raise BridgeInputError("arms_source_ambiguous", "arms 与 preset 只能二选一")
    if preset_name is not None:
        preset = store.get(preset_name)
        if preset is None:
            raise BridgeInputError("preset_not_found", f"电桥档 {preset_name!r} 不存在")
        _require_preset_type(preset, WHEATSTONE, "四臂惠斯通电桥接口")
        return preset.arms, preset_name
    if raw_arms is None:
        raise BridgeInputError(
            "arms_source_missing", "必须提供 arms（四臂阻值）或 preset（电桥档名）之一"
        )
    return validation.require_arm_set(raw_arms), None


def _resolve_kelvin(
    raw: dict | None, preset_name: str | None, *, need_rx: bool
) -> tuple[KelvinBridge, str | None, float | None]:
    """kelvin 与 preset 二选一，解析双电桥参数；返回档内电流（若取档）。"""
    if raw is not None and preset_name is not None:
        raise BridgeInputError("arms_source_ambiguous", "kelvin 与 preset 只能二选一")
    if preset_name is not None:
        preset = store.get(preset_name)
        if preset is None:
            raise BridgeInputError("preset_not_found", f"电桥档 {preset_name!r} 不存在")
        _require_preset_type(preset, KELVIN, "开尔文双电桥接口")
        bridge = preset.kelvin
        if need_rx and not (bridge.rx > 0.0):
            raise BridgeInputError(
                "kelvin_arm_not_positive",
                f"电桥档 {preset_name!r} 未登记待测电阻 rx，不能直接用于正算；"
                "请登记含 rx 的档或在请求中给出 kelvin 参数",
            )
        return bridge, preset_name, preset.source_current
    if raw is None:
        raise BridgeInputError(
            "arms_source_missing", "必须提供 kelvin（双电桥参数）或 preset（电桥档名）之一"
        )
    return validation.require_kelvin_bridge(raw, need_rx=need_rx), None, None


def _preset_response(preset: Preset) -> PresetResponse:
    return PresetResponse(
        name=preset.name,
        type=preset.type,
        arms=preset.arms.as_dict() if preset.arms is not None else None,
        kelvin=preset.kelvin.as_dict() if preset.kelvin is not None else None,
        source_current=preset.source_current,
        description=preset.description,
    )


def _safe_relative_error(calculated: float, reference: float) -> float:
    if reference == 0.0:
        return abs(calculated - reference)
    return abs((calculated - reference) / reference)


# --------------------------------------------------------------------------
# 元信息 / 健康检查
# --------------------------------------------------------------------------


@app.get("/")
def root() -> dict:
    return {
        "service": "电阻电桥核算服务",
        "version": "2.0.0",
        "bridge_types": [WHEATSTONE, KELVIN],
        "balance_conditions": {
            WHEATSTONE: balance_mod.BALANCE_CONDITION,
            KELVIN: "rx = (r1/r2)*rs + yoke*(r1*r4-r2*r3)/(r2*(r3+r4+yoke))",
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


# --------------------------------------------------------------------------
# 四臂惠斯通电桥（请求/响应字段、错误码与历史一致；额外附节点交叉核对）
# --------------------------------------------------------------------------


@app.post("/v1/bridge/output", response_model=ForwardResponse)
def bridge_output(req: ForwardRequest) -> ForwardResponse:
    """正算：开路不平衡输出；给检流计内阻时附戴维南等效下的实际偏转量。"""
    arms, preset_name = _resolve_arms(req.arms, req.preset)
    vs = validation.validate_source_voltage(req.source_voltage)
    rg = validation.validate_galvanometer(req.galvanometer_resistance)

    v_b = forward.divider_voltage_b(arms, vs)
    v_d = forward.divider_voltage_d(arms, vs)
    v_out = v_b - v_d
    prod_left, prod_right = balance_mod.balance_products(arms)

    notes: list[str] = []
    zero_source = vs == 0.0
    if zero_source:
        notes.append("桥源电压为零：输出为零，属正常情形而非错误")

    # 同一结果经通用节点方程底子独立复算（两种电桥共用的底子）
    nodal_result = wheatstone_nodal.analyze(arms, vs, rg)
    nodal_out = nodal_result.open_circuit_voltage
    out_err = _safe_relative_error(nodal_out, v_out)
    nodal_check = NodalCrossCheck(
        open_circuit_voltage=nodal_out,
        output_relative_error=out_err,
        thevenin_resistance=nodal_result.thevenin_resistance,
        galvanometer_current=nodal_result.loaded_current,
        galvanometer_relative_error=None,
    )

    galvanometer = None
    if rg is not None:
        current = thevenin.galvanometer_current(arms, vs, rg)
        galvanometer = GalvanometerResult(
            resistance=rg,
            thevenin_voltage=thevenin.thevenin_voltage(arms, vs),
            thevenin_resistance=thevenin.thevenin_resistance(arms),
            current=current,
            voltage=current * rg,
            method="closed_form",
        )
        ref_err = _safe_relative_error(nodal_result.loaded_current, current)
        nodal_check.galvanometer_relative_error = ref_err
        notes.append("检流计偏转量与电流成正比；电流由戴维南等效严格求得")

    notes.append(
        "开路输出与检流计电流同时由通用节点方程复算（见 nodal），"
        f"与闭式逐项一致（相对误差锁定 {NODAL_MATCH_REL_TOL:.0e}）"
    )

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
        bridge_type=WHEATSTONE,
        nodal=nodal_check,
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
        _require_preset_type(preset, WHEATSTONE, "四臂惠斯通电桥反解接口")
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
        bridge_type=WHEATSTONE,
    )


# --------------------------------------------------------------------------
# 开尔文双电桥
# --------------------------------------------------------------------------


@app.post("/v1/kelvin/output", response_model=KelvinForwardResponse)
def kelvin_output(req: KelvinForwardRequest) -> KelvinForwardResponse:
    """双电桥正算：节点方程给出开路输出、戴维南等效与检流计偏转。"""
    bridge, preset_name, _ = _resolve_kelvin(req.kelvin, req.preset, need_rx=True)
    current_src = validation.validate_source_current(req.source_current)
    rg = validation.validate_galvanometer(req.galvanometer_resistance)

    result = kelvin_forward.analyze(bridge, current_src, rg)
    v_m = result.node_voltages_open["M"]
    v_n = result.node_voltages_open["N"]
    v_out = result.open_circuit_voltage

    notes: list[str] = []
    zero_source = current_src == 0.0
    if zero_source:
        notes.append("恒流源电流为零：输出为零，属正常情形而非错误")
    notes.append("开路输出、戴维南等效与检流计电流均由整桥节点方程解得（含全部接触电阻元件）")

    galvanometer = None
    if rg is not None:
        galvanometer = GalvanometerResult(
            resistance=rg,
            thevenin_voltage=result.open_circuit_voltage,
            thevenin_resistance=result.thevenin_resistance,
            current=result.loaded_current,
            voltage=result.loaded_voltage,
            method="nodal",
        )

    balanced = v_out == 0.0 or kelvin_balance_is_balanced(bridge, v_out, current_src)

    return KelvinForwardResponse(
        kelvin=bridge.as_dict(),
        preset=preset_name,
        source_current=current_src,
        node_voltage_m=v_m,
        node_voltage_n=v_n,
        output_voltage=v_out,
        thevenin_resistance=result.thevenin_resistance,
        balanced=balanced,
        zero_source=zero_source,
        notes=notes,
        galvanometer=galvanometer,
    )


def kelvin_balance_is_balanced(bridge: KelvinBridge, v_out: float, source_current: float) -> bool:
    scale = abs(source_current) * max(bridge.rx, bridge.rs, bridge.yoke, 1e-300)
    return abs(v_out) <= 1e-9 * max(scale, 1e-300)


@app.post("/v1/kelvin/solve", response_model=KelvinSolveResponse)
def kelvin_solve(req: KelvinSolveRequest) -> KelvinSolveResponse:
    """双电桥反推：闭式反推 rx，并代回节点正算做自洽核查。"""
    bridge, preset_name, preset_current = _resolve_kelvin(req.kelvin, req.preset, need_rx=False)
    if preset_name is not None:
        source_current = preset_current if req.source_current is None else req.source_current
    else:
        if req.source_current is None:
            source_current = _PROBE_CURRENT
        else:
            source_current = req.source_current
    source_current = validation.validate_source_current(source_current)

    rx, main_term, correction = kelvin_balance.solve_unknown_rx(bridge)
    full = KelvinBridge(**{**bridge.as_dict(), "rx": rx})

    closure = kelvin_forward.open_circuit_output(full, source_current)
    closure_ig = kelvin_forward.galvanometer_current(full, source_current, _CLOSURE_RG)

    return KelvinSolveResponse(
        solved_resistance=rx,
        main_term=main_term,
        correction=correction,
        formula=kelvin_balance.FORMULA,
        balance_condition="V_M = V_N",
        kelvin=full.as_dict(),
        closure_source_current=source_current,
        closure_output_voltage=closure,
        closure_galvanometer_current=closure_ig,
    )


# --------------------------------------------------------------------------
# 电桥档
# --------------------------------------------------------------------------

_PRESET_NAME = Path(
    pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    description="电桥档名：字母数字开头，可含 - 和 _，最长 64 字符",
)


@app.put("/v1/presets/{name}", response_model=PresetResponse)
def put_preset(req: PresetRequest, name: str = _PRESET_NAME) -> PresetResponse:
    """登记（或整体替换）一套电桥档；不带 type 的老式请求按四臂处理。"""
    bridge_type = validation.validate_preset_type(req.type)
    if bridge_type == WHEATSTONE:
        if req.arms is None:
            raise BridgeInputError(
                "arms_source_missing", "四臂电桥档必须提供 arms（四臂阻值）"
            )
        arms = validation.require_arm_set(req.arms)
        return _preset_response(store.register(name, arms, req.description))

    # kelvin
    if req.kelvin is None:
        raise BridgeInputError(
            "arms_source_missing", "双电桥档必须提供 kelvin（双电桥参数）"
        )
    bridge = validation.require_kelvin_bridge(req.kelvin, need_rx=False)
    # 电桥档允许不带 rx（供反解取已知参数）；正算取该档时必须另行给出/已含 rx
    if req.source_current is None:
        raise BridgeInputError(
            "source_current_missing", "双电桥档必须提供 source_current（恒流源电流）"
        )
    source_current = validation.validate_source_current(req.source_current)
    return _preset_response(
        store.register_kelvin(name, bridge, source_current, req.description)
    )


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
