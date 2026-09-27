# 惠斯通电桥核算服务

计量实验室常驻服务，只做两件事，只经 HTTP 提供接口（无网页）：

1. **正算**：给定四个桥臂电阻与桥源电压，算开路不平衡输出电压；要求接入检流计时，用戴维南等效叠加检流计内阻，严格算出实际偏转量（偏转与电流成正比）。
2. **反解**：给定三个已知桥臂并要求桥平衡，按平衡条件的闭式表达式反推待测桥臂阻值——标定电阻的核心用法。

## 桥臂编号约定

```
            A (桥源正端)
           / \
          /   \
        R1     R2
        /       \
       B ───G─── D        B、D：输出端子；G：检流计（可选接入）
        \       /
        R3     R4
          \   /
           \ /
            C (桥源负端，参考地)
```

- 左分压支路 `A→R1→B→R3→C`：`V_B = Vs·R3/(R1+R3)`
- 右分压支路 `A→R2→D→R4→C`：`V_D = Vs·R4/(R2+R4)`
- **开路输出** `V_out = V_B − V_D = Vs·(R3/(R1+R3) − R4/(R2+R4))`，正值表示 B 电位高于 D
- **平衡条件**：相对臂（对角臂）乘积相等 **`R1·R4 = R2·R3`**，此时输出为零。相对臂对是 `(R1,R4)` 与 `(R2,R3)`，不是相邻臂
- **检流计**（内阻 `R_g`）：`V_th = V_out`，`R_th = (R1‖R3)+(R2‖R4)`，`I_g = V_th/(R_th+R_g)`，`V_g = I_g·R_g`
- **反解闭式**：待求臂 = 另一对对角臂之积 ÷ 自身对角伙伴，如 `R4 = R2·R3/R1`

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/bridge/output` | 正算：开路输出；带 `galvanometer_resistance` 时附检流计结果 |
| POST | `/v1/bridge/solve` | 反解：三已知臂 + 平衡目标 ⇒ 待测臂，并代回正算自洽核查 |
| PUT | `/v1/presets/{name}` | 登记/替换电桥档（命名四臂配置，进程内存，重启不保留） |
| GET | `/v1/presets`、`/v1/presets/{name}` | 检索电桥档 |
| DELETE | `/v1/presets/{name}` | 删除电桥档 |
| GET | `/healthz` | 健康检查 |

### 正算示例

```bash
curl -s localhost:8000/v1/bridge/output -H 'Content-Type: application/json' -d '{
  "arms": {"r1": 100, "r2": 200, "r3": 300, "r4": 500},
  "source_voltage": 12,
  "galvanometer_resistance": 150
}'
```

`arms` 与 `preset`（电桥档名）二选一。桥源电压为零时返回零输出并以 `zero_source`/`notes` 标明（不是错误）；负值表示极性反接，允许。

### 反解示例

```bash
curl -s localhost:8000/v1/bridge/solve -H 'Content-Type: application/json' -d '{
  "unknown_arm": "r4",
  "known_arms": {"r1": 100, "r2": 200, "r3": 300}
}'
# → solved_resistance = 600（r4 = r2*r3/r1），closure_output_voltage = 0
```

### 错误响应

非法输入在计算前被挡住，统一返回 `{"error": {"code", "message"}}`（HTTP 400；电桥档不存在为 404）：
`arm_not_positive`（臂阻非正）、`arm_missing`（缺臂）、`arm_unknown`、`arm_not_finite`、
`source_voltage_not_finite`、`galvanometer_not_positive`、`arms_source_ambiguous`/`arms_source_missing`、
`solve_unknown_arm_invalid`、`solve_known_arms_mismatch`、`solve_target_inconsistent`（反推目标不自洽）、
`preset_not_found`。

## 构建与运行

```bash
docker build -t wheatstone-bridge .        # 一键构建；构建过程会先跑全部判据测试，不过则构建失败
docker run --rm -p 8000:8000 wheatstone-bridge
```

本地开发（Python 3.12）：

```bash
pip install -r requirements-dev.txt
python -m pytest          # 跑判据测试
uvicorn app.main:app      # 起服务，文档在 /docs
```

## 判据测试（tests/）

- 相对臂乘积相等 ⇒ 开路输出为零（含四臂相等的手算基准，钉入回归）
- 固定三臂单独增大待测臂 ⇒ 输出单调变化并在平衡点符号翻转
- 桥源翻倍 ⇒ 同一失衡程度下输出绝对值翻倍
- 反解出的待测臂代回正算 ⇒ 输出归零（正算/反解自洽闭合，模块级与接口级各一份）
- 戴维南检流计结果与直接节点分析交叉核对
- 电桥档并存时各档阻值互相独立

## 文件职责

```
app/
  bridge/topology.py    桥臂编号约定与四臂数据结构（含拓扑图）
  bridge/forward.py     正算：开路输出的分压差
  bridge/thevenin.py    检流计：戴维南等效求解
  bridge/balance.py     反解：平衡条件与待测臂闭式解
  presets.py            电桥档登记检索（进程内存）
  validation.py         参数校验（计算前挡非法输入）
  schemas.py            请求/响应模型
  main.py               HTTP 层：收发请求与编排调用
```
