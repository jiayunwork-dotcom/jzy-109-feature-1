"""开尔文双电桥 HTTP 接口端到端：正算、反推、错误码、类型不符、电桥档。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 比例相等、轭线非零的手算基准
BENCH = {"rs": 0.001, "r1": 1000, "r2": 1000, "r3": 300, "r4": 300, "yoke": 0.002}


def _output(params, current=1.0, **over):
    body = {"kelvin": params, "source_current": current}
    body.update(over)
    return client.post("/v1/kelvin/output", json=body)


# ---- 基准与自洽 ----

def test_api_equal_ratio_benchmark_zero_output():
    """手算基准：rs=1mΩ、内外比例都=1、轭线 2mΩ ⇒ rx=1mΩ，零输出。"""
    p = {**BENCH, "rx": 0.001}
    resp = _output(p, galvanometer_resistance=50.0)
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_voltage"] == pytest.approx(0.0, abs=1e-17)
    assert data["balanced"] is True
    assert data["bridge_type"] == "kelvin"
    assert data["galvanometer"]["current"] == pytest.approx(0.0, abs=1e-17)
    assert data["galvanometer"]["method"] == "nodal"
    assert data["thevenin_resistance"] > 0.0


def test_api_solve_then_output_closure():
    resp = client.post("/v1/kelvin/solve", json={"kelvin": BENCH})
    assert resp.status_code == 200
    data = resp.json()
    assert data["solved_resistance"] == pytest.approx(0.001)
    assert data["main_term"] == pytest.approx(0.001)
    assert data["correction"] == pytest.approx(0.0)
    assert data["closure_output_voltage"] == pytest.approx(0.0, abs=1e-15)
    assert data["closure_galvanometer_current"] == pytest.approx(0.0, abs=1e-15)
    # 代回正算接口
    check = _output(data["kelvin"])
    assert check.json()["output_voltage"] == pytest.approx(0.0, abs=1e-15)


def test_api_yoke_sweep_equal_ratio_invariant():
    values = []
    for yoke in (0.0, 0.002, 1.0, 100.0):
        resp = client.post("/v1/kelvin/solve", json={"kelvin": {**BENCH, "yoke": yoke}})
        values.append(resp.json()["solved_resistance"])
    assert values == pytest.approx([0.001] * 4, abs=1e-15)


def test_api_mismatched_ratio_correction_changes_with_yoke():
    p = {"rs": 0.01, "r1": 1000, "r2": 1000, "r3": 300, "r4": 200}
    c0 = client.post("/v1/kelvin/solve", json={"kelvin": {**p, "yoke": 0.0}}).json()
    c1 = client.post("/v1/kelvin/solve", json={"kelvin": {**p, "yoke": 0.02}}).json()
    assert c0["correction"] == 0.0
    assert c1["correction"] != 0.0
    expected = 0.02 * (1000 * 200 - 1000 * 300) / (1000 * (300 + 200 + 0.02))
    assert c1["correction"] == pytest.approx(expected)


def test_api_current_contacts_invariant_potential_contacts_shift():
    p = {**BENCH}
    base = client.post("/v1/kelvin/solve", json={"kelvin": p}).json()["solved_resistance"]
    # 只增大两个电流端接触（含外侧 rc1 与内侧 rc2），比例一致时平衡点不动
    moved = client.post(
        "/v1/kelvin/solve", json={"kelvin": {**p, "rc1": 0.05, "rc2": 0.05}}
    ).json()["solved_resistance"]
    assert moved == pytest.approx(base, abs=1e-15)
    # 只增大一个电位端接触，平衡点偏移
    shifted = client.post(
        "/v1/kelvin/solve", json={"kelvin": {**p, "rp1": 0.5}}
    ).json()["solved_resistance"]
    assert shifted != pytest.approx(base)
    # 期望：把 rp1 串进 r1 后按闭式手算（等比例下轭线项为零）
    r1_eff, r2, rs, yoke = 1000.5, 1000.0, 0.001, 0.002
    expected = (r1_eff / r2) * rs + yoke * (r1_eff * 300 - r2 * 300) / (
        r2 * (300 + 300 + yoke)
    )
    assert shifted == pytest.approx(expected, rel=1e-12)


def test_api_zero_and_negative_source():
    p = {**BENCH, "rx": 0.0008}
    zero = _output(p, current=0.0).json()
    assert zero["output_voltage"] == 0.0 and zero["zero_source"] is True
    pos = _output(p, current=1.0).json()["output_voltage"]
    neg = _output(p, current=-1.0).json()["output_voltage"]
    assert neg == pytest.approx(-pos, rel=1e-12)


# ---- 非法输入：求解前挡住，独立错误码 ----

def test_api_arm_not_positive_codes():
    for field in ("r1", "r2", "r3", "r4", "rs"):
        resp = _output({**BENCH, "rx": 0.001, field: 0.0})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "kelvin_arm_not_positive", field
        resp = _output({**BENCH, "rx": 0.001, field: -1.0})
        assert resp.json()["error"]["code"] == "kelvin_arm_not_positive", field


def test_api_arm_non_finite():
    body = json.dumps({"kelvin": {**BENCH, "rx": float("nan")}, "source_current": 1.0},
                      allow_nan=True)
    resp = client.post("/v1/kelvin/output", content=body,
                       headers={"Content-Type": "application/json"})
    # rx 非有限：Pydantic 层（NaN 不允许）或校验层；本服务对正算要求 rx 正有限
    assert resp.status_code in (400, 422)


def test_api_yoke_negative_rejected():
    resp = _output({**BENCH, "rx": 0.001, "yoke": -1e-3})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "kelvin_yoke_negative"


def test_api_contact_negative_rejected_independently():
    for field in ("rc1", "rc2", "rc3", "rc4", "rp1", "rp2", "rp3", "rp4"):
        resp = _output({**BENCH, "rx": 0.001, field: -1e-6})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "kelvin_contact_negative", field


def test_api_source_current_not_finite():
    body = json.dumps({"kelvin": {**BENCH, "rx": 0.001}, "source_current": float("inf")},
                      allow_nan=True)
    resp = client.post("/v1/kelvin/output", content=body,
                       headers={"Content-Type": "application/json"})
    assert resp.status_code in (400, 422)


def test_api_missing_field_and_unknown_field():
    p = {k: v for k, v in BENCH.items() if k != "r3"}
    resp = _output({**p, "rx": 0.001})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "kelvin_field_missing"
    resp = _output({**BENCH, "rx": 0.001, "bogus": 1.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "kelvin_field_unknown"


# ---- 病态 ----

def test_api_ill_conditioned_returns_reason_not_nan():
    # 主回路电阻与比例臂相差 12 个数量级以上 ⇒ 条件数超 1e12
    p = {"rx": 1e14, "rs": 1e14, "r1": 100, "r2": 100, "r3": 100, "r4": 100, "yoke": 1e14}
    resp = _output(p)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "network_ill_conditioned"
    assert "条件数" in err["message"]
    assert "NaN" not in err["message"] and "nan" not in err["message"]


def test_api_ill_conditioned_solve_also_blocked():
    p = {"rs": 1e14, "r1": 100, "r2": 100, "r3": 100, "r4": 100, "yoke": 1e14}
    # 反推本身是闭式不病态，但代回节点正算核查会解病态网络
    resp = client.post("/v1/kelvin/solve", json={"kelvin": p})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "network_ill_conditioned"


# ---- 电桥档：类型标注与类型不符 ----

def test_api_legacy_preset_defaults_to_wheatstone():
    """不带类型的老式登记请求照旧按四臂处理。"""
    resp = client.put("/v1/presets/ws-std",
                      json={"arms": {"r1": 100, "r2": 200, "r3": 300, "r4": 600}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "wheatstone"
    assert data["arms"] is not None and data["kelvin"] is None


def test_api_register_and_list_kelvin_preset():
    resp = client.put("/v1/presets/kv-std", json={
        "type": "kelvin",
        "kelvin": {**BENCH, "rx": 0.001},
        "source_current": 1.0,
        "description": "双电桥基准档",
    })
    assert resp.status_code == 200
    assert resp.json()["type"] == "kelvin"
    assert resp.json()["kelvin"]["r1"] == 1000
    assert resp.json()["source_current"] == 1.0

    listed = {p["name"]: p["type"] for p in client.get("/v1/presets").json()}
    assert listed.get("kv-std") == "kelvin"

    out = client.post("/v1/kelvin/output",
                      json={"preset": "kv-std", "source_current": 1.0})
    assert out.status_code == 200
    assert out.json()["output_voltage"] == pytest.approx(0.0, abs=1e-17)


def test_api_type_mismatch_wheatstone_preset_on_kelvin():
    client.put("/v1/presets/ws", json={"arms": {"r1": 1, "r2": 2, "r3": 3, "r4": 6}})
    resp = client.post("/v1/kelvin/output",
                       json={"preset": "ws", "source_current": 1.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "preset_type_mismatch"
    resp = client.post("/v1/kelvin/solve", json={"preset": "ws"})
    assert resp.json()["error"]["code"] == "preset_type_mismatch"


def test_api_type_mismatch_kelvin_preset_on_wheatstone():
    client.put("/v1/presets/kv", json={
        "type": "kelvin", "kelvin": {**BENCH, "rx": 0.001}, "source_current": 1.0,
    })
    resp = client.post("/v1/bridge/output",
                       json={"preset": "kv", "source_voltage": 12.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "preset_type_mismatch"
    resp = client.post("/v1/bridge/solve",
                       json={"unknown_arm": "r4", "preset": "kv"})
    assert resp.json()["error"]["code"] == "preset_type_mismatch"


def test_api_kelvin_preset_requires_parts():
    resp = client.put("/v1/presets/bad1", json={"type": "kelvin", "source_current": 1.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "arms_source_missing"
    resp = client.put("/v1/presets/bad2", json={"type": "kelvin", "kelvin": {**BENCH, "rx": 0.001}})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "source_current_missing"


def test_api_solve_kelvin_with_preset_uses_its_current():
    client.put("/v1/presets/kv2", json={
        "type": "kelvin",
        "kelvin": {k: v for k, v in BENCH.items()},  # 反解档无需 rx
        "source_current": 2.5,
    })
    resp = client.post("/v1/kelvin/solve", json={"preset": "kv2"})
    assert resp.status_code == 200
    assert resp.json()["closure_source_current"] == 2.5
    assert resp.json()["closure_output_voltage"] == pytest.approx(0.0, abs=1e-15)
