"""双电桥 HTTP 接口、电桥档类型标注与类型不符错误的端到端判据。"""
import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

RATIO_EQUAL = {"R1": 100.0, "R2": 100.0, "r3": 10.0, "r4": 10.0}
CONFIG_EQUAL = {"ratio_arms": RATIO_EQUAL, "standard_resistance": 0.1, "yoke_resistance": 0.02}
CONFIG_MISMATCH = {"ratio_arms": {"R1": 100.0, "R2": 100.0, "r3": 5.0, "r4": 10.0},
                   "standard_resistance": 0.1, "yoke_resistance": 0.01}


def _config_body(**overrides):
    # 深拷贝，避免就地改动污染模块级常量、串到其它用例
    body = copy.deepcopy(CONFIG_EQUAL)
    body.update(overrides)
    return body


# ---- 反推与自洽闭合（接口级） ----

def test_solve_equal_ratio_hand_benchmark():
    resp = client.post("/v1/kelvin/solve", json={"config": CONFIG_EQUAL})
    assert resp.status_code == 200
    data = resp.json()
    assert data["bridge_type"] == "kelvin"
    assert data["solved_resistance"] == pytest.approx(0.1)
    assert data["main_term"] == pytest.approx(0.1)
    assert data["correction_term"] == 0.0
    assert data["closure_output_voltage"] == pytest.approx(0.0, abs=1e-12)
    assert data["closure_galvanometer_current"] == pytest.approx(0.0, abs=1e-13)
    assert data["config"]["contacts"]["rx_co_c"] == 0.0


def test_solve_mismatched_ratio_correction():
    resp = client.post("/v1/kelvin/solve", json={"config": CONFIG_MISMATCH})
    data = resp.json()
    # Ry·(R1·r4−R2·r3)/[R2·(r3+r4+Ry)] = 0.01·500/(100·15.01)
    assert data["correction_term"] == pytest.approx(0.0033311125916055963, rel=1e-12)
    assert data["solved_resistance"] == pytest.approx(0.1033311125916056, rel=1e-12)


def test_forward_solved_rx_zero_galvanometer_current():
    solved = client.post("/v1/kelvin/solve", json={"config": CONFIG_MISMATCH}).json()
    resp = client.post("/v1/kelvin/output", json={
        "config": CONFIG_MISMATCH,
        "unknown_resistance": solved["solved_resistance"],
        "source_current": 1.0,
        "galvanometer_resistance": 50.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_voltage"] == pytest.approx(0.0, abs=1e-12)
    assert data["galvanometer"]["current"] == pytest.approx(0.0, abs=1e-13)
    assert data["balanced"] is True


def test_forward_zero_and_negative_source():
    body = {"config": CONFIG_EQUAL, "unknown_resistance": 0.12, "source_current": 0.0,
            "galvanometer_resistance": 50.0}
    data = client.post("/v1/kelvin/output", json=body).json()
    assert data["zero_source"] is True
    assert data["output_voltage"] == 0.0
    assert data["galvanometer"]["current"] == 0.0

    pos = client.post("/v1/kelvin/output", json={
        "config": CONFIG_EQUAL, "unknown_resistance": 0.12, "source_current": 2.0}).json()
    neg = client.post("/v1/kelvin/output", json={
        "config": CONFIG_EQUAL, "unknown_resistance": 0.12, "source_current": -2.0}).json()
    assert neg["output_voltage"] == pytest.approx(-pos["output_voltage"], rel=1e-12)


# ---- 计算前挡住非法输入（独立错误码） ----

@pytest.mark.parametrize("mutator,code", [
    (lambda b: b["config"]["ratio_arms"].__setitem__("R1", 0.0), "kelvin_ratio_arm_not_positive"),
    (lambda b: b.__setitem__("unknown_resistance", 0.0), "kelvin_unknown_not_positive"),
])
def test_forward_validation_codes(mutator, code):
    body = {"config": _config_body(contacts={}), "unknown_resistance": 0.1,
            "source_current": 1.0}
    mutator(body)
    resp = client.post("/v1/kelvin/output", json=body)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code


@pytest.mark.parametrize("key,value,code", [
    ("standard_resistance", -1.0, "kelvin_standard_not_positive"),
    ("yoke_resistance", -0.01, "kelvin_yoke_negative"),
])
def test_forward_config_field_validation(key, value, code):
    body = {"config": _config_body(**{key: value}), "unknown_resistance": 0.1,
            "source_current": 1.0}
    resp = client.post("/v1/kelvin/output", json=body)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code


def test_forward_contact_negative_validation():
    body = {"config": _config_body(contacts={"rx_co_c": -0.001}),
            "unknown_resistance": 0.1, "source_current": 1.0}
    resp = client.post("/v1/kelvin/output", json=body)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "kelvin_contact_negative"


def test_source_current_non_finite_rejected_before_solve():
    import json

    body = json.dumps({
        "config": CONFIG_EQUAL, "unknown_resistance": 0.1,
        "source_current": float("nan")}, allow_nan=True)
    resp = client.post(
        "/v1/kelvin/output", content=body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "kelvin_source_current_not_finite"


def test_ill_conditioned_returns_reason_not_linear_algebra_leak():
    """内臂汇合点 k 经 1e13 Ω 臂近虚接（条件数约 3e14）→ 带原因的病态错误。

    返回体里不能出现 NaN/Inf 或线性代数异常，必须给出 code 与原因。
    """
    bad_config = {
        "ratio_arms": {"R1": 100.0, "R2": 100.0, "r3": 1.0e13, "r4": 1.0e13},
        "standard_resistance": 0.1,
        "yoke_resistance": 0.02,
    }
    resp = client.post("/v1/kelvin/output", json={
        "config": bad_config, "unknown_resistance": 0.1, "source_current": 1.0})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "circuit_ill_conditioned"
    assert error["details"]["pivot_ratio"] > 1.0e12
    assert "病态" in error["message"]
    assert "NaN" not in resp.text and "Infinity" not in resp.text


def test_singular_returns_reason_when_junction_completely_floating():
    """检流计端口一侧完全不接比例臂（用零电导无法表达，改用极大且另一侧断开）。

    r3、r4 取 1e18 Ω（电导相对下溢为零）时 k 与网络无有效连接 → 结构奇异。
    """
    singular_config = {
        "ratio_arms": {"R1": 100.0, "R2": 100.0, "r3": 1.0e18, "r4": 1.0e18},
        "standard_resistance": 0.1,
        "yoke_resistance": 0.02,
    }
    resp = client.post("/v1/kelvin/output", json={
        "config": singular_config, "unknown_resistance": 0.1, "source_current": 1.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "circuit_singular"


# ---- 电桥档类型 ----

def test_legacy_preset_without_type_is_wheatstone():
    resp = client.put("/v1/presets/legacy", json={
        "arms": {"r1": 1000.0, "r2": 1000.0, "r3": 1000.0, "r4": 1000.0}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["bridge_type"] == "wheatstone"
    assert data["arms"] == {"r1": 1000.0, "r2": 1000.0, "r3": 1000.0, "r4": 1000.0}
    assert data["kelvin_config"] is None
    assert client.get("/v1/presets/legacy").json()["bridge_type"] == "wheatstone"


def test_kelvin_preset_crud_and_listed_with_type():
    resp = client.put("/v1/presets/shunt-1mohm", json={
        "bridge_type": "kelvin",
        "kelvin_config": CONFIG_EQUAL,
        "description": "分流器毫欧档",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["bridge_type"] == "kelvin"
    assert data["arms"] is None
    assert data["kelvin_config"]["ratio_arms"] == RATIO_EQUAL

    listed = {p["name"]: p["bridge_type"] for p in client.get("/v1/presets").json()}
    assert listed["shunt-1mohm"] == "kelvin"

    # 用档做双电桥反推与正算
    solved = client.post("/v1/kelvin/solve", json={"preset": "shunt-1mohm"}).json()
    assert solved["preset"] == "shunt-1mohm"
    assert solved["solved_resistance"] == pytest.approx(0.1)


def test_wrong_type_preset_rejected_on_both_families():
    client.put("/v1/presets/w", json={
        "arms": {"r1": 100.0, "r2": 200.0, "r3": 300.0, "r4": 600.0}})
    client.put("/v1/presets/k", json={
        "bridge_type": "kelvin", "kelvin_config": CONFIG_EQUAL})

    # 四臂接口取 kelvin 档
    resp = client.post("/v1/bridge/output", json={"preset": "k", "source_voltage": 1.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "preset_type_mismatch"
    resp = client.post("/v1/bridge/solve", json={"unknown_arm": "r4", "preset": "k"})
    assert resp.json()["error"]["code"] == "preset_type_mismatch"

    # 双电桥接口取 wheatstone 档
    resp = client.post("/v1/kelvin/output", json={
        "preset": "w", "unknown_resistance": 0.1, "source_current": 1.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "preset_type_mismatch"
    resp = client.post("/v1/kelvin/solve", json={"preset": "w"})
    assert resp.json()["error"]["code"] == "preset_type_mismatch"


def test_preset_registration_field_type_conflict():
    # kelvin 档只给 arms
    resp = client.put("/v1/presets/x1", json={"bridge_type": "kelvin", "arms": {"r1": 1}})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "preset_fields_type_conflict"
    # kelvin 档什么配置都不给
    resp = client.put("/v1/presets/x0", json={"bridge_type": "kelvin"})
    assert resp.json()["error"]["code"] == "kelvin_config_missing"
    # wheatstone 档误给 kelvin_config
    resp = client.put("/v1/presets/x2", json={
        "arms": {"r1": 1.0, "r2": 1.0, "r3": 1.0, "r4": 1.0},
        "kelvin_config": CONFIG_EQUAL})
    assert resp.json()["error"]["code"] == "preset_fields_type_conflict"


def test_config_and_preset_ambiguous_or_missing():
    resp = client.post("/v1/kelvin/solve", json={"config": CONFIG_EQUAL, "preset": "k"})
    assert resp.json()["error"]["code"] == "arms_source_ambiguous"
    resp = client.post("/v1/kelvin/solve", json={})
    assert resp.json()["error"]["code"] == "arms_source_missing"
