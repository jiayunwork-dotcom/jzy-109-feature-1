r"""节点方程求解：平衡标度 + 选主元消元 + 条件数估计的奇异/病态判定。

为什么这样选（README「奇异与病态判定」一节给出完整理由、代价与反例）：

1. **选主元消元**保证数值稳定，是给出解的主体；
2. **装配期平衡标度（equilibration）**把电导矩阵的量纲消掉：先按行最大
   元、再按列最大元缩放到 1，使后续判据与电阻单位（毫欧/兆欧）无关；
3. **条件数而不是主元阈值**判病态。电导矩阵是对称正定（SPD）的节点导纳
   矩阵，单独的主元阈值有两个无法接受的失败模式：

   - 行标度主元对对角占优的电导矩阵几乎恒等于 1，真正 1e15 量级展度的
     桥也触发不了；
   - 原始（无量纲化前的）主元带电导量纲，单位一换阈值就失效。

   因此用标度后矩阵的 **1-范数条件数下确界估计（Hager 迭代估计）**判定：
   估计值超过 :data:`CONDITION_LIMIT` 即判近奇异。该估计只复用消元做若干
   次三角求解（本服务矩阵至多十几阶，成本可忽略），不需要重量级数值库。

4. **残差守卫保留但只兜底**：解算结果必须为有限数，且标度化回代残差不
   能超过 :data:`RESIDUAL_TOL`。注意小残差不能用来证明良态（病态解也常有
   极小残差），所以条件数才是主判据。

判定结果：

========================== ==============================================
现象                        判定
========================== ==============================================
自由节点无电导（整行为零）  奇异 ``network_singular``
等电位收缩后出现电位矛盾    奇异 ``network_singular``
标度后条件数估计 > 阈值     近奇异 ``network_ill_conditioned``
消元出现非有限值/残差超限   近奇异 ``network_ill_conditioned``
========================== ==============================================

绝不把 ZeroDivisionError、无穷大或 NaN 透给上层：一切数值上的不可靠都
转成带 ``code`` 与中文原因的 :class:`NetworkEquationError`。
"""
from __future__ import annotations

import math

from app.circuit.errors import NetworkEquationError
from app.circuit.network import Assembled, Network

#: 标度后 1-范数条件数上限：超过即判近奇异（病态）。
#: 双精度机器精度约 2.2e-16，取 1e12 意味着结果至多还能保住约 4 位有效
#: 数字；对毫欧级标定这是「不可信」的保守界线。正常桥路 κ 通常 < 1e6。
CONDITION_LIMIT = 1e12

#: 残差守卫（标度化后的相对残差）。只兜底，不用作病态主判据。
RESIDUAL_TOL = 1e-9

#: Hager 条件数估计的最大迭代次数（通常 2~3 次即收敛）。
HAGER_ITERATIONS = 5


def _equilibrate(matrix: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    """返回 (B, row_scale, col_scale)：B[i][j] = G[i][j]/(row_i·col_j)，行列最大元≈1。"""
    n = len(matrix)
    row_scale = [max((abs(matrix[i][j]) for j in range(n)), default=0.0) for i in range(n)]
    if any(s == 0.0 for s in row_scale):
        k = next(i for i, s in enumerate(row_scale) if s == 0.0)
        raise NetworkEquationError(
            "network_singular",
            f"节点方程奇异：第 {k} 行系数全为零（存在悬空节点或零电导支路），电位不唯一",
        )
    mid = [[matrix[i][j] / row_scale[i] for j in range(n)] for i in range(n)]
    col_scale = [max(abs(mid[i][j]) for i in range(n)) for j in range(n)]
    balanced = [
        [mid[i][j] / col_scale[j] if col_scale[j] != 0.0 else mid[i][j] for j in range(n)]
        for i in range(n)
    ]
    return balanced, row_scale, col_scale


def _lu_factor(matrix: list[list[float]]) -> tuple[list[list[float]], list[int]]:
    """高斯消元（部分主元），原地得到上三角因子；返回 (矩阵, 主元行置换)。"""
    n = len(matrix)
    m = [row[:] for row in matrix]
    perm = list(range(n))
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(m[r][col]))
        pivot = m[pivot_row][col]
        if not math.isfinite(pivot) or pivot == 0.0:
            raise NetworkEquationError(
                "network_singular",
                f"节点方程奇异：消元到第 {col} 个主元时无可用非零主元",
            )
        if pivot_row != col:
            m[col], m[pivot_row] = m[pivot_row], m[col]
            perm[col], perm[pivot_row] = perm[pivot_row], perm[col]
        for row in range(col + 1, n):
            factor = m[row][col] / pivot
            if factor != 0.0:
                m[row][col] = factor
                for k in range(col + 1, n):
                    m[row][k] -= factor * m[col][k]
    return m, perm


def _lu_solve(lu: list[list[float]], perm: list[int], rhs: list[float]) -> list[float]:
    """用已分解的 LU（含行置换）解线性方程组。"""
    n = len(lu)
    y = [0.0] * n
    for i in range(n):
        s = rhs[perm[i]]
        for j in range(i):
            s -= lu[i][j] * y[j]
        y[i] = s
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = y[i]
        for j in range(i + 1, n):
            s -= lu[i][j] * x[j]
        piv = lu[i][i]
        x[i] = s / piv
    return x


def _estimate_condition(balanced: list[list[float]], lu: list[list[float]],
                        perm: list[int]) -> float:
    """标度后矩阵的 1-范数条件数估计 κ₁(B) ≈ ‖B‖₁·‖B⁻¹‖₁（Hager 估计器）。"""
    n = len(balanced)
    norm_b = max(sum(abs(balanced[i][j]) for i in range(n)) for j in range(n))

    # Hager 迭代估计 ‖B⁻¹‖₁
    x = [1.0 / n] * n
    gamma = 0.0
    prev_j = -1
    for _ in range(HAGER_ITERATIONS):
        w = _lu_solve(lu, perm, x)
        gamma = sum(abs(v) for v in w)
        sign = [1.0 if v >= 0.0 else -1.0 for v in w]
        z = _lu_solve(lu, perm, sign)
        abs_z = [abs(v) for v in z]
        j = max(range(n), key=lambda i: abs_z[i])
        if abs_z[j] <= sum(z[i] * x[i] for i in range(n)):
            break
        if j == prev_j:
            break
        prev_j = j
        x = [0.0] * n
        x[j] = 1.0
    return norm_b * gamma


def gaussian_solve(assembled: Assembled) -> dict[int, float]:
    """解 G·V = I，返回 {自由分量根节点编号: 电位}。奇异/病态抛错。"""
    n = len(assembled.matrix)
    if n == 0:
        return {}

    balanced, row_scale, col_scale = _equilibrate(assembled.matrix)
    lu, perm = _lu_factor(balanced)

    kappa = _estimate_condition(balanced, lu, perm)
    if not math.isfinite(kappa) or kappa > CONDITION_LIMIT:
        raise NetworkEquationError(
            "network_ill_conditioned",
            f"节点方程近奇异：平衡标度后的 1-范数条件数估计为 "
            f"{kappa:.3e}，超过可信上限 {CONDITION_LIMIT:.0e}；桥路中存在与其余电导"
            "相差十二个数量级以上的极弱耦合支路，双精度消元的有效数字不足，拒绝给出"
            "不可靠数值（请检查是否误填了与毫欧级阻值相差极大的臂阻/接触电阻）",
        )

    # 标度后的右端 d_i = b_i / row_scale_i，解 B·y = d，再还原 x_j = y_j / col_scale_j
    rhs_scaled = [assembled.rhs[i] / row_scale[i] for i in range(n)]
    y = _lu_solve(lu, perm, rhs_scaled)
    x = [y[j] / col_scale[j] if col_scale[j] != 0.0 else y[j] for j in range(n)]

    for val in x:
        if not math.isfinite(val):
            raise NetworkEquationError(
                "network_ill_conditioned",
                "消元结果中出现非有限值（上溢）：电阻参数量级过于悬殊，拒绝给出不可靠数值",
            )

    # 残差守卫（相对量纲），只兜底捕获估计器漏掉的异常
    rhs_scale = max((abs(v) for v in assembled.rhs), default=0.0)
    gx_scale = max(
        (abs(sum(assembled.matrix[i][j] * x[j] for j in range(n))) for i in range(n)),
        default=0.0,
    )
    tol = RESIDUAL_TOL * max(rhs_scale, gx_scale, 1e-300)
    for i in range(n):
        residual = abs(sum(assembled.matrix[i][j] * x[j] for j in range(n)) - assembled.rhs[i])
        if residual > tol:
            raise NetworkEquationError(
                "network_ill_conditioned",
                f"节点方程近奇异：标度化回代相对残差 {residual:.3e} 超过守卫容差，"
                "拒绝给出不可靠数值",
            )

    free_roots = sorted(
        r for r in set(assembled.roots.values()) if r not in assembled.fixed_voltage
    )
    return {root: x[k] for k, root in enumerate(free_roots)}


def node_voltages(network: Network) -> dict[str, float]:
    """完整求解一张网络，返回所有命名节点的电位（伏）。"""
    assembled = network.assemble()
    sol = gaussian_solve(assembled)
    voltages: dict[str, float] = {}
    for idx in range(len(network._names)):
        name = network._names[idx]
        root = assembled.roots[idx]
        if root in assembled.fixed_voltage:
            voltages[name] = assembled.fixed_voltage[root]
        else:
            voltages[name] = sol[root]
    return voltages
