# 电桥核算服务（四臂惠斯通电桥 / 开尔文双电桥）

计量实验室常驻服务，只经 HTTP 提供接口（无网页）。支持两种电桥：

1. **四臂惠斯通电桥**（一般阻值）：正算开路不平衡输出、戴维南等效下的检流计偏转；按平衡条件闭式反推待测臂。
2. **开尔文双电桥**（分流器、母排等毫欧级低值电阻，四端测量）：正算走整张电路的节点方程；按开尔文平衡闭式反推待测低值电阻，轭线（连接线）电阻带来一项可计算的修正。

两种电桥的**正算共用同一套通用节点方程求解底子**（`app/bridge/nodal.py`），不各自抄公式；四臂电桥的历史闭式结果保留为对外结果与对照，自动化测试把两条路径锁在相对误差 1e-9 内。

## 一、四臂惠斯通电桥

### 桥臂编号约定

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
- **平衡条件**：相对臂（对角臂）乘积相等 **`R1·R4 = R2·R3`**
- **检流计**（内阻 `R_g`）：`V_th = V_out`，`R_th = (R1‖R3)+(R2‖R4)`，`I_g = V_th/(R_th+R_g)`
- **反解闭式**：如 `R4 = R2·R3/R1`

## 二、开尔文双电桥

毫欧级低值电阻必须**四端测量**：每个电阻体有两个电流端（走主回路大电流）和两个电位端（只取压降、几乎无电流），使引线/接触电阻不再与被测电阻同量级地混入结果。

### 拓扑与编号约定

```
              恒流源 I_s
          SRC+ ───────► GND
            │            ▲
        rx_co_c          │ rs_co_c          外侧电流端接触电阻
            ▼            │
          X_CO ──Rx── X_CI                    主回路四个主节点
            │            │
          X_PO          X_PI                  理想取压点（与同端电流端等电位）
            │            │
         rx_po_c       rx_pi_c                电位端接触电阻（串入比例臂）
            │            │
           R1           r3                    外臂 R1 / 内臂 r3（待测侧）
            │            │
            └────► j ◄───┘                    j：两只【外】臂汇合点
                   │
                   G                          检流计（可选，开路不接入）
                   │
            ┌────► k ◄───┐                    k：两只【内】臂汇合点
            │            │
           R2           r4                    外臂 R2 / 内臂 r4（标准侧）
            │            │
         rs_po_c       rs_pi_c
            │            │
          S_PO          S_PI
            │            │
          S_CO ──Rs── S_CI
            ▲            ▲
        rs_co_c      rs_ci_c
            │            │
           GND       yoke_s ◄── Ry ── yoke_x ── rx_ci_c ── X_CI
                                                  轭线 Ry 串在两内侧电流端之间
```

- 主回路：`SRC+ → X_CO → Rx → X_CI →（rx_ci_c）→ Ry →（rs_ci_c）→ S_CI → Rs → S_CO → GND`
- 主节点（沿主回路）：`X_CO`（待测**外**侧电流端）、`X_CI`（待测**内**侧）、`S_CI`（标准**内**侧）、`S_CO`（标准**外**侧）
- 取压点：`X_PO / X_PI / S_PO / S_PI` 分别与同端电流端等电位（理想四端短接）
- **外比例臂**：`R1`（X_CO 侧）、`R2`（S_CO 侧）在 **j** 汇合
- **内比例臂**：`r3`（X_CI 侧）、`r4`（S_CI 侧）在 **k** 汇合
- **检流计跨 j、k**。关键：j 是两只外臂的汇合点，k 是两只内臂的汇合点，不能把外臂与内臂挂到检流计同一侧
- **8 个接触电阻**（非负，不填按 0），全部作为**独立元件进入节点方程**：

  | 名称 | 位置 | 串入 |
  |---|---|---|
  | `rx_co_c` / `rs_co_c` | 待测/标准·外**电流**端 | 主回路 |
  | `rx_ci_c` / `rs_ci_c` | 待测/标准·内**电流**端 | 与轭线串联 |
  | `rx_po_c` / `rs_po_c` | 待测/标准·外**电位**端 | 外臂 R1 / R2 支路 |
  | `rx_pi_c` / `rs_pi_c` | 待测/标准·内**电位**端 | 内臂 r3 / r4 支路 |

### 平衡反推闭式（推导）

检流计零电流即 `Vj = Vk`。记主回路电流为 `I`、内臂支路电流为 `i`（轭线中电流相应为 `I−i`），对两个内侧节点列 KCL 并沿比例臂写压降，消去 `I、i`，得标准开尔文平衡式：

```
Rx = (R1/R2)·Rs + Ry·(R1·r4 − R2·r3) / [ R2·(r3 + r4 + Ry) ]
        └──主比例项──┘   └────────────轭线修正项────────────┘
```

- **主比例项** `(R1/R2)·Rs`：外臂比例对标准电阻的换算。
- **轭线修正项**：正比于轭线电阻 `Ry`（随其增大而增大），并正比于内外臂比例之差 `(R1·r4 − R2·r3)`。**内外比例一致（`R1/R2 = r3/r4`）时修正项严格为零**，此时把 `Ry` 从 0 调到远大于 `Rx`，反推值完全不变。

计入接触电阻后，闭式侧按其物理串入位置做代数归并（正算侧不归并，始终是独立元件）：

```
R1' = R1 + rx_po_c          R2' = R2 + rs_po_c
r3' = r3 + rx_pi_c          r4' = r4 + rs_pi_c
Ry' = Ry + rx_ci_c + rs_ci_c
Rx = (R1'/R2')·Rs + Ry'·(R1'·r4' − R2'·r3') / [ R2'·(r3'+r4'+Ry') ]
```

外侧电流端接触电阻 `rx_co_c / rs_co_c` 不进入公式：它们只改变恒流源两端承担的电压，不动任何取压点电位——这正是四端测量的价值。

> 正算一侧**不使用**该闭式解，而是解整张电路（含 8 个接触电阻）的节点方程；反推值代回正算必须得到零开路输出与零检流计电流（自洽闭合测试）。

## 三、节点方程怎么解、怎么判奇异/病态（方案取舍）

正算把电路描述成「节点 + 电阻 + 电流源 + 固定电位点」的线性电阻网络，集合成节点电导矩阵 `G·v = i`。求解器在 `app/bridge/nodal.py`，**纯标准库实现，不引入 numpy 等重量级数值库**。

**采用方案：完全选主元（行列对称交换）的高斯消元，配合两道阈值。**

- 零欧电阻（短接线、理想取压线）先用并查集合并成超节点，绝不往矩阵里写 `1/0`。
- 电导矩阵是对称半正定（SPD）M 矩阵，对称选主元后各主元为正、量级按序排列，数值稳定性好，且**消元与判奇异/病态在同一遍扫描内完成**，不需要额外解方程组或单独估条件数，规模就十几个节点，开销可忽略。
- 两道判定：
  1. 某步主元不超过矩阵最大元的 **`PIVOT_ZERO = 1e-15`**（双精度近零）→ **结构奇异** `circuit_singular`。物理上对应：存在与参考点没有任何电导连接的孤立节点组，或两个电位不同的固定点被零欧短接成同一点。
  2. 消元后主元量级比（最大主元/最小主元，SPD 阵的廉价条件数估计）超过 **`COND_LIMIT = 1e12`** → **病态** `circuit_ill_conditioned`，错误体带回实测 `pivot_ratio` 与阈值。物理上对应取压节点近虚接（只通过超大电阻漏电到网络），仍有直流通路、矩阵非奇异，但有效数字不足以支撑毫欧标定，宁可拒绝。

**为什么不选「先估条件数再判定」**：要拿可靠的 2-范数条件数得做特征分解，或用 Lanczos/幂迭代反复解方程，对这点规模是杀鸡用牛刀，还要引入 numpy；便宜的「行范数估计」对 SPD M 矩阵偏松，可能漏掉近悬浮节点。选主元消元在求解的同时天然产出主元这一现成的尺度信息，零额外库、零额外扫描。

**代价**：主元比是启发式阈值，不是严格条件数；它对「两端都强接地、仅彼此弱耦合」这类其实良态的网络不会误报（其 Schur 补主元仍稳健），但对尺度极悬殊的合法网络偏保守。被判病态时调用方拿到的是带原因（含实测主元比）的 `400` 错误，而不是线性代数异常或 `NaN/Inf`——后者一律在求解器内翻译成 `NetworkError`，不允许透出。

**同一个近奇异桥换方案会怎样**：以「某检流计汇合点只经 `1e13 Ω` 臂挂到网络」为例，本方案测得主元比约 `3e12`，判**病态**并拒绝；若改用「仅在严格奇异时报错、其余照常出数」的方案，消元仍会返回一个有限电压值，但该值只信赖约 2~3 位有效数字，毫欧级标定会被静默污染。把弱臂加大到 `1e18 Ω`（电导相对下溢），本方案与严格奇异方案都会报 `circuit_singular`，二者在真无连接处结论一致，分歧只在「能算但不可信」的中间地带——本服务选择在那一段就明确报错。

## 四、接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/bridge/output` | 四臂正算：开路输出；带检流计内阻时附偏转量 |
| POST | `/v1/bridge/solve` | 四臂反解：三已知臂 + 平衡 ⇒ 待测臂 |
| POST | `/v1/kelvin/output` | **双电桥正算**：开路输出、戴维南、检流计电流（节点方程） |
| POST | `/v1/kelvin/solve` | **双电桥反推**：平衡闭式 ⇒ Rx，代回节点正算闭合 |
| PUT | `/v1/presets/{name}` | 登记/替换电桥档（带 `bridge_type`） |
| GET | `/v1/presets`、`/v1/presets/{name}` | 检索电桥档（列表含每档类型） |
| DELETE | `/v1/presets/{name}` | 删除电桥档 |
| GET | `/healthz` | 健康检查 |

**电桥档类型**：`bridge_type` 取 `wheatstone`（默认）或 `kelvin`。老式**不带** `bridge_type` 的登记请求照旧按四臂处理，字段与行为与改动前完全一致。拿 kelvin 档调四臂接口、或拿 wheatstone 档调双电桥接口，返回 `preset_type_mismatch`（400），不静默取错字段。

### 双电桥反推示例

```bash
curl -s localhost:8000/v1/kelvin/solve -H 'Content-Type: application/json' -d '{
  "config": {
    "ratio_arms": {"R1": 100, "R2": 100, "r3": 5, "r4": 10},
    "standard_resistance": 0.1,
    "yoke_resistance": 0.01,
    "contacts": {"rx_po_c": 0.0, "rx_ci_c": 0.0}
  }
}'
# → solved_resistance ≈ 0.1033311126（主项 0.1 + 轭线修正 0.0033311）
#   closure_output_voltage = 0，closure_galvanometer_current = 0
```

`config` 与 `preset`（kelvin 档名）二选一；`contacts` 整段可省（8 项默认 0）。

### 双电桥正算示例

```bash
curl -s localhost:8000/v1/kelvin/output -H 'Content-Type: application/json' -d '{
  "config": {
    "ratio_arms": {"R1": 100, "R2": 100, "r3": 10, "r4": 10},
    "standard_resistance": 0.1,
    "yoke_resistance": 0.02
  },
  "unknown_resistance": 0.1,
  "source_current": 1.0,
  "galvanometer_resistance": 50
}'
```

恒流源电流为零返回零输出并以 `zero_source`/`notes` 标明（不是错误）；负值表示电流反向，允许。

### 四臂正算 / 反解示例

```bash
curl -s localhost:8000/v1/bridge/output -H 'Content-Type: application/json' -d '{
  "arms": {"r1": 100, "r2": 200, "r3": 300, "r4": 500},
  "source_voltage": 12, "galvanometer_resistance": 150
}'

curl -s localhost:8000/v1/bridge/solve -H 'Content-Type: application/json' -d '{
  "unknown_arm": "r4", "known_arms": {"r1": 100, "r2": 200, "r3": 300}
}'
# → solved_resistance = 600，closure_output_voltage = 0
```

### 错误响应

统一 `{"error": {"code", "message"[, "details"]}}`（HTTP 400；电桥档不存在 404；请求结构错误 422）。

- 四臂既有错误码（保持不变）：`arm_not_positive`、`arm_missing`、`arm_unknown`、`arm_not_finite`、`source_voltage_not_finite`、`galvanometer_not_positive`、`arms_source_ambiguous`/`arms_source_missing`、`solve_unknown_arm_invalid`、`solve_known_arms_mismatch`、`solve_target_inconsistent`、`preset_not_found`。
- 双电桥新增（互相独立、计算前挡住）：`kelvin_ratio_arm_not_finite`/`kelvin_ratio_arm_not_positive`（及 `..._missing`/`..._unknown`）、`kelvin_standard_not_finite`/`..._not_positive`、`kelvin_unknown_not_finite`/`..._not_positive`、`kelvin_yoke_not_finite`/`kelvin_yoke_negative`、`kelvin_contact_not_finite`/`kelvin_contact_negative`（及 `..._unknown`/`..._invalid`）、`kelvin_source_current_not_finite`。
- 电桥档：`preset_type_mismatch`（档类型与接口不符）、`preset_fields_type_conflict`（登记时 arms/kelvin_config 与类型冲突）、`kelvin_config_missing`。
- 节点求解：`circuit_singular`（结构奇异）、`circuit_ill_conditioned`（病态，带主元比）。

## 五、构建与运行

```bash
docker build -t bridge-service .        # 一键构建；先跑全部测试，不过则构建失败
docker run --rm -p 8000:8000 bridge-service
```

本地（Python 3.12）：

```bash
pip install -r requirements-dev.txt
python -m pytest          # 全部判据测试
uvicorn app.main:app      # 服务，文档 /docs
```

## 六、判据测试（tests/）

四臂（历史判据全部保留）：相对臂乘积相等 ⇒ 输出为零；待测臂扫描过平衡点符号翻转；桥源翻倍输出翻倍；反解代回归零；戴维南结果与直接节点分析交叉核对；电桥档独立。

新增：
- 四臂正算的**通用节点方程路径与闭式逐项一致**（多组臂值 × 电压 × 检流计，容差 1e-9）。
- 双电桥等比例时轭线电阻从 0 扫到 ≫ Rx，反推值不变；失配时随轭线变化且变化量等于闭式修正项。
- 只增两个电流端接触电阻 ⇒ 平衡点不动；只增某电位端接触电阻 ⇒ 偏移量等于串进对应比例臂的闭式结果。
- 反推 Rx 代回双电桥节点正算 ⇒ 开路输出与检流计电流双零。
- 手算基准（比例相等、轭线非零）钉入回归。
- 各非法输入独立错误码；近虚接判 `circuit_ill_conditioned`、断连判 `circuit_singular`，均带原因；档类型不符 `preset_type_mismatch`。

## 七、文件职责

```
app/
  bridge/topology.py           四臂编号约定与 ArmSet（含拓扑图）
  bridge/forward.py            四臂正算闭式（分压差，对照路径）
  bridge/thevenin.py           四臂戴维南/检流计闭式（对照路径）
  bridge/balance.py            四臂反推闭式
  bridge/nodal.py              【共用底子】通用电阻网络节点方程 + 选主元消元 + 奇异/病态判定
  bridge/wheatstone_circuit.py 四臂 → 通用网络（正算的节点方程路径）
  bridge/kelvin_topology.py    双电桥拓扑、编号、8 接触电阻与网络构造
  bridge/kelvin_balance.py     双电桥反推闭式（含推导、有效臂归并）
  bridge/kelvin_forward.py     双电桥正算（节点方程：开路/戴维南/检流计）
  bridge/kelvin_validation.py  双电桥参数校验（独立错误码）
  presets.py                   电桥档登记检索（带 bridge_type）
  validation.py                四臂参数校验
  schemas.py                   请求/响应模型
  main.py                      HTTP 层：编排、类型校验、错误转换
tests/
  test_nodal.py                通用求解器：手算网络/零欧/等效电阻/奇异/病态
  test_wheatstone_nodal.py     四臂两路径一致性
  test_kelvin_balance.py       双电桥反推判据（轭线/接触电阻/基准）
  test_kelvin_forward.py       双电桥正算判据（自洽闭合/戴维南/标度）
  test_kelvin_validation.py    双电桥校验错误码
  test_kelvin_api.py           双电桥接口、档类型、类型不符
```
