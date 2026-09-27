"""HTTP 层：只负责收发请求与编排调用，电学计算全部在 app.bridge 各模块中。"""
from __future__ import annotations

from fastapi import FastAPI, Path, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import validation
from app.bridge import balance as balance_mod
from app.bridge import forward, thevenin
from app.bridge.topology import ARM_NAMES, ArmSet
from app.presets import Preset, PresetStore
from app.schemas import (
    ForwardRequest,
    ForwardResponse,
    GalvanometerResult,
    PresetRequest,
    PresetResponse,
    SolveRequest,
    SolveResponse,
)
from app.validation import BridgeInputError

APP_DESCRIPTION = """惠斯通电桥核算服务（仅 HTTP 接口，无网页）。

桥臂编号约定::

            A (桥源正端)
           / \\
         R1     R2
         /       \\
        B ───G─── D     B、D：输出端子；G：检流计（可选）
         \\       /
         R3     R4
           \\   /
            C (桥源负端)

开路输出 V_out = Vs·(R3/(R1+R3) − R4/(R2+R4))；
平衡条件为相对臂乘积相等：R1·R4 = R2·R3。
"""

#: 反解自洽核查用的探针桥源电压（伏）
_PROBE_VOLTAGE = 1.0

app = FastAPI(title="惠斯通电桥核算服务", version="1.0.0", description=APP_DESCRIPTION)

#: 电桥档登记处（进程内存，跨重启不保留）
store = PresetStore()

_STATUS_BY_CODE = {"preset_not_found": 404}


@app.exception_handler(BridgeInputError)
async def bridge_input_error_handler(_request: Request, exc: BridgeInputError) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_CODE.get(exc.code, 400),
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


def _resolve_arms(raw_arms: dict | None, preset_name: str | None) -> tuple[ArmSet, str | None]:
    """arms 与 preset 二选一，解析出经校验的四臂集合。"""
    if raw_arms is not None and preset_name is not None:
        raise BridgeInputError("arms_source_ambiguous", "arms 与 preset 只能二选一")
    if preset_name is not None:
        preset = store.get(preset_name)
        if preset is None:
            raise BridgeInputError("preset_not_found", f"电桥档 {preset_name!r} 不存在")
        return preset.arms, preset_name
    if raw_arms is None:
        raise BridgeInputError(
            "arms_source_missing", "必须提供 arms（四臂阻值）或 preset（电桥档名）之一"
        )
    return validation.require_arm_set(raw_arms), None


def _preset_response(preset: Preset) -> PresetResponse:
    return PresetResponse(name=preset.name, arms=preset.arms.as_dict(), description=preset.description)


@app.get("/")
def root() -> dict:
    return {
        "service": "惠斯通电桥核算服务",
        "version": "1.0.0",
        "balance_condition": balance_mod.BALANCE_CONDITION,
        "endpoints": {
            "output": "POST /v1/bridge/output",
            "solve": "POST /v1/bridge/solve",
            "presets": "PUT/GET/DELETE /v1/presets[/{name}]",
        },
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


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
        # 桥源为零不是错误：直接给出零输出并标明
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


_PRESET_NAME = Path(
    pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    description="电桥档名：字母数字开头，可含 - 和 _，最长 64 字符",
)


@app.put("/v1/presets/{name}", response_model=PresetResponse)
def put_preset(req: PresetRequest, name: str = _PRESET_NAME) -> PresetResponse:
    """登记（或整体替换）一套电桥档；各档阻值互相独立。"""
    arms = validation.require_arm_set(req.arms)
    return _preset_response(store.register(name, arms, req.description))


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
