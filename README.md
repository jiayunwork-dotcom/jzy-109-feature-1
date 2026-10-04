# 电阻电桥核算服务

计量实验室常驻服务，只经 HTTP 提供接口（无网页），支持两种电桥：

1. **四臂惠斯通电桥（wheatstone）**：给定四臂与桥源电压，算开路不平衡输出；接检流计时用戴维南等效严格算实际偏转。反解按闭式平衡条件反推待测臂。
2. **开尔文双电桥（kelvin）**：标定分流器、母排这类**毫欧级四端低值电阻**。引线和接触电阻与被测值同量级，四臂惠斯通公式不可用；双电桥把八个接触点各自作为元件进网，正算解整桥节点方程，反解用开尔文闭式。

两种电桥的**正算**（开路输出、戴维南等效、检流计电流）统一走一套通用电阻
网络的节点方程求解（`app/circuit/`），不在旧公式旁另抄一套；四臂闭式保留
作对照，测试把两条路径逐项锁死（相对误差 ≤ 1e-9）。

## 四臂惠斯通电桥：编号约定

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

- 开路输出 `V_out = Vs·(R3/(R1+R3) − R4/(R2+R4))`
- 平衡条件：相对臂乘积相等 **`R1·R4 = R2·R3`**
- 检流计：`V_th = V_out`，`R_th = (R1‖R3)+(R2‖R4)`，`I_g = V_th/(R_th+R_g)`
- 反解闭式：如 `R4 = R2·R3/R1`

## 开尔文双电桥：拓扑与编号约定

低值电阻是**四端器件**：两个电流端 C 走主回路大电流，两个电位端 P 只取
电位（比例臂支路电流极小），从而把引线/接触电阻赶进不影响测量的支路。

```
  S+ ──rc1── n1 ─────── R_x ─────── n2 ──rc2── y2
   │         (P1)                (P2)            │
  恒流源                                          轭线 r_y
  I_s                                            │
   │         (P3)                (P4)           y3 ──rc3── n3
  S- ──rc4── n4 ─────── R_s ─────────────────── n3

  外比例臂：n1(P1) ─rp1─R1─ M ─R2─rp3─ n4(P3)     （R1、R2 汇合成 M）
  内比例臂：n2(P2) ─rp2─R3─ N ─R4─rp4─ n3(P4)     （R3、R4 汇合成 N）
  检流计：    M ───────────── G ───────────── N   （正方向 M → N）
```

- **n1/n2**：R_x 的外侧（C1，朝 S+）/内侧（C2，朝轭线）电流端；
  **n3/n4**：R_s 的内侧（C3，朝轭线）/外侧（C4，朝 S-）电流端。
- **电位端**：P1、P2 属 R_x（外、内）；P3、P4 属 R_s（外、内）。
- 主回路：`S+ → rc1 → n1 → R_x → n2 → rc2 → 轭线 r_y → rc3 → n3 → R_s → n4 → rc4 → S-`。
- **主比例 = R1/R2，内比例 = R3/R4**；平衡条件 **V_M = V_N**。
- 八个接触电阻（不填按零，作为元件进节点方程，**不**事后加减）：
  电流端 `rc1 rc2 rc3 rc4`；电位端 `rp1 rp2 rp3 rp4`。

### 反解闭式（推导）

外臂无电源，`V_M = V1·R2/(R1+R2)`；内臂支路电流连续，
`V_N = (V2·R4 + V3·R3)/(R3+R4)`。将这两个分压式代入 n1、n2、n3 三个主回路
节点的 KCL 并消去 V1、V2、V3 与源电流 J，平衡 V_M = V_N 给出关于 R_x 的
线性方程，解得

```
R_x = (R1/R2)·R_s  +  r_y·(R1·R4 − R2·R3) / [ R2·(R3 + R4 + r_y) ]
      └── 主比例项 ──┘   └──────────── 轭线修正项 Δ ─────────────┘
```

记 p = R1/R2、q = R3/R4，则 `Δ = r_y·(p−q)·R4/(R3+R4+r_y)`。

- **内外比例一致（p = q）时 Δ ≡ 0**：轭线电阻从 0 调到远大于被测值，反推值
  严格不变（测试 `test_equal_ratio_yoke_sweep_does_not_move_balance`）。
- p ≠ q 时 Δ 随轭线单调变化，轭线为零则 Δ 为零。
- 接触电阻并入对应元件后代入同一闭式：`R1→R1+rp1，R2→R2+rp3，
  R3→R3+rp2，R4→R4+rp4，r_y→r_y+rc2+rc3`；外侧电流端接触 rc1、rc4 在恒流源
  支路，不移动平衡点。

闭式只用于反解；正算一律解整桥节点方程。

## 节点方程底子与奇异/病态判定（方案、理由、代价）

`app/circuit/` 把电路抽象为「电阻 + 零电阻收缩 + 钳位电压 + 电流注入」，
装配节点导纳方程 G·V = I 后求解。求解器采用：

1. **平衡标度（equilibration）**：按行、再按列最大元把矩阵缩放到 1，消去
   电导量纲，使判据与电阻单位（毫欧/兆欧）无关；
2. **部分主元高斯消元**：保证数值稳定并给出解；
3. **标度后 1-范数条件数估计（Hager 迭代）**：估计值 > `1e12` 判近奇异
   （病态），返回 `network_ill_conditioned`；双精度机器精度约 2.2e-16，取
   1e12 意味着结果至多剩约 4 位有效数字，对毫欧标定已不可信；
4. 整行为零/悬空节点、钳位矛盾判**奇异** `network_singular`；另留相对残差
   守卫只作兜底。

**为什么不选「选主元 + 主元阈值」**：节点导纳矩阵对称正定且对角占优，
行标度主元几乎恒等于 1，真正差 15 个数量级的极弱耦合也触发不了；而未量纲
化的原始主元带电导单位，换单位阈值就失效。**为什么不先算精确条件数**：
精确 κ 要求逆（多一遍 O(n³)），本服务矩阵最多十几阶，Hager 估计只复用已有
LU 做几次三角回代即可，不引入重量级数值库。

代价与反例（也是测试钉住的边界）：

- **本方案判为病态的一类桥**：两个各自强电导的节点簇只靠一条极弱支路相连
  （浮簇），例如主回路电阻与比例臂相差 ≥ 12 个数量级，κ 随弱耦合比线性
  增长越界（`test_ill_conditioned_floating_cluster`、API 病态用例）。
- **同一近奇异桥若改用「主元阈值」会怎样**：它的标度主元仍接近 1，阈值法
  **不会报错**，而是静默吐出只剩几位有效数字的结果——这正是本方案不用它的
  原因。反过来，单纯的「所有臂同比放大 1e6 倍」κ 不变，本方案不误报
  （`test_well_conditioned_large_but_uniform_spread_ok`）。
- 检流计电流用 `V_th/(R_th+R_g)`（两个量都来自节点解），而**不**用带载端
  电压除以（可能极小的）R_g 反推：后者在 R_g ≪ R_th 时把端电压舍入误差
  放大成大的相对误差。

任何线性代数异常、无穷大、NaN 都不会透出：统一转成带 `code` 与中文原因的
错误响应（HTTP 422）。

## 接口

| 方法 | 路径 | 电桥 | 说明 |
|---|---|---|---|
| POST | `/v1/bridge/output` | 四臂 | 正算：开路输出 + 检流计（附节点交叉核对 `nodal`） |
| POST | `/v1/bridge/solve` | 四臂 | 闭式反解待测臂，代回正算自洽核查 |
| POST | `/v1/kelvin/output` | 双电桥 | 节点正算：开路输出、R_th、检流计电流 |
| POST | `/v1/kelvin/solve` | 双电桥 | 闭式反推 rx，代回节点正算核查（开路+接表均归零） |
| PUT | `/v1/presets/{name}` | 两者 | 登记/替换电桥档（`type` 标注；不带类型按四臂） |
| GET | `/v1/presets`、`/v1/presets/{name}` | 两者 | 检索（响应含 `type`） |
| DELETE | `/v1/presets/{name}` | 两者 | 删除 |
| GET | `/healthz` | — | 健康检查 |

### 四臂正算/反解（字段与旧版完全一致）

```bash
curl -s localhost:8000/v1/bridge/output -H 'Content-Type: application/json' -d '{
  "arms": {"r1": 100, "r2": 200, "r3": 300, "r4": 500},
  "source_voltage": 12, "galvanometer_resistance": 150
}'
```

响应额外带 `bridge_type:"wheatstone"` 与 `nodal`（节点方程复算及与闭式的
相对误差，锁在 1e-9）。

### 双电桥反解

```bash
curl -s localhost:8000/v1/kelvin/solve -H 'Content-Type: application/json' -d '{
  "kelvin": {"rs": 0.001, "r1": 1000, "r2": 1000, "r3": 300, "r4": 300,
             "yoke": 0.002, "rc1": 0.0005, "rp1": 0.0001}
}'
# → solved_resistance=0.001，main_term=0.001，correction=0，
#   closure_output_voltage≈0，closure_galvanometer_current≈0
```

### 双电桥正算

```bash
curl -s localhost:8000/v1/kelvin/output -H 'Content-Type: application/json' -d '{
  "kelvin": {"rx": 0.0012, "rs": 0.001, "r1": 1000, "r2": 1000, "r3": 300, "r4": 300,
             "yoke": 0.002},
  "source_current": 1.0, "galvanometer_resistance": 50
}'
```

### 电桥档与类型把关

```bash
# 老式登记（不带 type）= 四臂
curl -s -X PUT localhost:8000/v1/presets/ws-std -H 'Content-Type: application/json' -d '{
  "arms": {"r1": 100, "r2": 200, "r3": 300, "r4": 600}}'
# 双电桥档
curl -s -X PUT localhost:8000/v1/presets/kv-std -H 'Content-Type: application/json' -d '{
  "type": "kelvin",
  "kelvin": {"rs": 0.001, "r1": 1000, "r2": 1000, "r3": 300, "r4": 300, "yoke": 0.002},
  "source_current": 1.0}'
```

拿双电桥档调四臂接口、或反过来，返回 `preset_type_mismatch`（400），不静默
取错字段。列表/查询响应里每档都带 `type`。

### 错误码

统一 `{"error":{"code","message"}}`（业务错误 400，电桥档不存在 404，
节点方程奇异/病态与请求体结构错误 422）：

- 四臂（不变）：`arm_not_positive`、`arm_missing`、`arm_unknown`、
  `arm_not_finite`、`source_voltage_not_finite`、`galvanometer_not_positive`、
  `arms_source_ambiguous`/`arms_source_missing`、`solve_*`、`preset_not_found`。
- 双电桥：`kelvin_arm_not_positive`/`kelvin_arm_not_finite`（比例臂、标准/待测
  电阻）、`kelvin_yoke_negative`/`kelvin_yoke_not_finite`、
  `kelvin_contact_negative`/`kelvin_contact_not_finite`、
  `source_current_not_finite`、`kelvin_field_missing`/`kelvin_field_unknown`、
  `preset_type_mismatch`、`bridge_type_invalid`、`source_current_missing`。
- 求解器：`network_singular`（悬空/钳位矛盾）、`network_ill_conditioned`（条件数越界/上溢/残差超限）。

## 构建与运行

```bash
docker build -t resistor-bridge .        # 一键构建；先跑全部测试，不过则构建失败
docker run --rm -p 8000:8000 resistor-bridge
```

本地开发（Python 3.12）：

```bash
pip install -r requirements-dev.txt
python -m pytest          # 全部判据测试
uvicorn app.main:app
```

## 文件职责

```
app/
  circuit/network.py            通用电阻网络：元件登记、零电阻并查集收缩、G·V=I 装配
  circuit/solver.py             平衡标度 + 选主元消元 + 条件数估计（奇异/病态判定）
  circuit/analysis.py           开路/置零/带载三种激励 → V_th、R_th、I_g（两桥共用）
  bridge/topology.py            四臂编号约定与 ArmSet
  bridge/wheatstone_network.py  四臂 → 通用网络适配
  bridge/forward.py             四臂正算闭式（保留作对照）
  bridge/thevenin.py            四臂戴维南闭式（保留作对照）
  bridge/wheatstone_nodal.py    四臂节点正算（新底子）
  bridge/balance.py             四臂反解闭式
  bridge/kelvin_topology.py     双电桥拓扑、编号约定、KelvinBridge
  bridge/kelvin_network.py      双电桥 → 通用网络适配（八个接触电阻元件）
  bridge/kelvin_balance.py      双电桥反解闭式与推导
  bridge/kelvin_forward.py      双电桥节点正算
  presets.py                    电桥档（带类型，线程安全内存登记）
  validation.py                 两种电桥的参数校验（求解前挡住）
  schemas.py                    请求/响应模型
  main.py                       HTTP 层：编排与类型把关
tests/                          判据测试（旧测试断言不删不改，新增各模块独立文件）
```
