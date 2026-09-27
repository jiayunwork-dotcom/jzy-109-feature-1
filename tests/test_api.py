"""HTTP 接口端到端：正算、反解、电桥档、错误响应与三条核心关系。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ARMS_BALANCED = {"r1": 100.0, "r2": 200.0, "r3": 300.0, "r4": 600.0}
ARMS_UNBALANCED = {"r1": 100.0, "r2": 200.0, "r3": 300.0, "r4": 500.0}


def _output(**overrides):
    body = {"arms": ARMS_UNBALANCED, "source_voltage": 12.0}
    body.update(overrides)
    return client.post("/v1/bridge/output", json=body)


# ---- 三条核心关系（接口级） ----

def test_api_opposite_products_equal_output_zero():
    resp = _output(arms=ARMS_BALANCED)
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_voltage"] == 0.0
    assert data["balanced"] is True
    assert data["balance_products"] == {"r1*r4": 60000.0, "r2*r3": 60000.0}


def test_api_source_doubling_doubles_output_magnitude():
    v1 = _output(source_voltage=6.0).json()["output_voltage"]
    v2 = _output(source_voltage=12.0).json()["output_voltage"]
    assert v1 != 0.0
    assert abs(v2) == pytest.approx(2.0 * abs(v1), rel=1e-15)


def test_api_solve_then_output_closure():
    """反解接口解出的待测臂，经正算接口复核输出归零：正算与反解自洽闭合。"""
    resp = client.post(
        "/v1/bridge/solve",
        json={"unknown_arm": "r4", "known_arms": {"r1": 100.0, "r2": 200.0, "r3": 300.0}},
    )
    assert resp.status_code == 200
    solved = resp.json()
    assert solved["solved_resistance"] == 600.0
    assert solved["formula"] == "r4 = r2*r3/r1"
    assert solved["closure_output_voltage"] == pytest.approx(0.0, abs=1e-12)
    check = _output(arms=solved["arms"])
    assert check.json()["output_voltage"] == 0.0
    assert check.json()["balanced"] is True


# ---- 正算细节 ----

def test_api_output_hand_computable():
    resp = _output(arms={"r1": 100.0, "r2": 200.0, "r3": 300.0, "r4": 100.0})
    data = resp.json()
    assert data["divider_voltage_b"] == 9.0
    assert data["divider_voltage_d"] == 4.0
    assert data["output_voltage"] == 5.0
    assert data["balanced"] is False
    assert data["zero_source"] is False
    assert data["galvanometer"] is None


def test_api_galvanometer_thevenin():
    resp = _output(galvanometer_resistance=150.0)
    data = resp.json()
    gal = data["galvanometer"]
    assert gal["resistance"] == 150.0
    # V_th 即开路输出；I_g = V_th/(R_th+R_g)；V_g = I_g·R_g
    assert gal["thevenin_voltage"] == data["output_voltage"]
    assert gal["current"] == pytest.approx(
        gal["thevenin_voltage"] / (gal["thevenin_resistance"] + 150.0), rel=1e-12
    )
    assert gal["voltage"] == pytest.approx(gal["current"] * 150.0, rel=1e-12)


def test_api_zero_source_gives_zero_output_with_note():
    resp = _output(source_voltage=0.0, galvanometer_resistance=50.0)
    assert resp.status_code == 200
    data = resp.json()
    assert data["zero_source"] is True
    assert data["output_voltage"] == 0.0
    assert data["galvanometer"]["current"] == 0.0
    assert any("桥源电压为零" in note for note in data["notes"])


def test_api_negative_source_allowed_as_reversed_polarity():
    pos = _output(source_voltage=12.0).json()["output_voltage"]
    neg = _output(source_voltage=-12.0).json()["output_voltage"]
    assert neg == pytest.approx(-pos, rel=1e-15)


# ---- 非法输入：计算前挡住并讲清原因 ----

def test_api_arm_not_positive():
    resp = _output(arms={"r1": 100.0, "r2": 200.0, "r3": 0.0, "r4": 500.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "arm_not_positive"


def test_api_arm_missing():
    resp = _output(arms={"r1": 100.0, "r2": 200.0, "r3": 300.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "arm_missing"


def test_api_non_finite_source_voltage():
    body = json.dumps(
        {"arms": ARMS_UNBALANCED, "source_voltage": float("nan")}, allow_nan=True
    )
    resp = client.post(
        "/v1/bridge/output", content=body, headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "source_voltage_not_finite"


def test_api_arms_source_ambiguous_or_missing():
    client.put("/v1/presets/std", json={"arms": ARMS_BALANCED})
    resp = _output(preset="std")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "arms_source_ambiguous"
    resp = client.post("/v1/bridge/output", json={"source_voltage": 12.0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "arms_source_missing"


def test_api_solve_inconsistent_target():
    resp = client.post(
        "/v1/bridge/solve",
        json={
            "unknown_arm": "r4",
            "known_arms": {"r1": 1.0, "r2": 2.0, "r3": 3.0, "r4": 9.0},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "solve_target_inconsistent"
    resp = client.post(
        "/v1/bridge/solve",
        json={"unknown_arm": "r4", "known_arms": {"r1": 1.0, "r2": 2.0}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "solve_known_arms_mismatch"
    resp = client.post(
        "/v1/bridge/solve",
        json={
            "unknown_arm": "r4",
            "known_arms": {"r1": 1.0, "r2": 2.0, "r3": 3.0},
            "target_output_voltage": 0.5,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "solve_target_inconsistent"


# ---- 电桥档 ----

def test_api_preset_crud_and_independence():
    assert client.put("/v1/presets/std-1k", json={
        "arms": {"r1": 1000.0, "r2": 1000.0, "r3": 1000.0, "r4": 1000.0},
        "description": "四臂相等基准档",
    }).status_code == 200
    assert client.put("/v1/presets/work", json={"arms": ARMS_UNBALANCED}).status_code == 200

    # 用档做正算：std-1k 平衡、work 失衡，互不影响
    bal = _output(arms=None, preset="std-1k").json()
    work = _output(arms=None, preset="work").json()
    assert bal["output_voltage"] == 0.0 and bal["preset"] == "std-1k"
    assert work["output_voltage"] != 0.0 and work["preset"] == "work"

    # 覆盖 work 后，std-1k 的阻值不串
    client.put("/v1/presets/work", json={"arms": {"r1": 1.0, "r2": 2.0, "r3": 3.0, "r4": 4.0}})
    again = client.get("/v1/presets/std-1k").json()
    assert again["arms"] == {"r1": 1000.0, "r2": 1000.0, "r3": 1000.0, "r4": 1000.0}

    names = [p["name"] for p in client.get("/v1/presets").json()]
    assert names == ["std-1k", "work"]
    assert client.delete("/v1/presets/work").status_code == 204
    assert client.get("/v1/presets/work").status_code == 404


def test_api_preset_not_found():
    resp = _output(arms=None, preset="nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "preset_not_found"


def test_api_solve_with_preset_knowns():
    """反解也可取电桥档的其余三臂为已知。"""
    client.put("/v1/presets/cal", json={"arms": ARMS_BALANCED})
    resp = client.post("/v1/bridge/solve", json={"unknown_arm": "r4", "preset": "cal"})
    assert resp.status_code == 200
    assert resp.json()["solved_resistance"] == 600.0


def test_api_all_equal_benchmark_pinned():
    """回归基准：四臂相等时输出为零（可手算核对）。"""
    resp = _output(arms={"r1": 1000.0, "r2": 1000.0, "r3": 1000.0, "r4": 1000.0},
                   source_voltage=10.0, galvanometer_resistance=100.0)
    data = resp.json()
    assert data["output_voltage"] == 0.0
    assert data["divider_voltage_b"] == data["divider_voltage_d"] == 5.0
    assert data["galvanometer"]["current"] == 0.0
    assert data["balanced"] is True
