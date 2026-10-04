r"""通用线性电阻网络求解：节点方程 + 选主元高斯消元。

这是正算一层的共用底子：四臂惠斯通电桥与开尔文双电桥都先描述成
同一种「电阻 + 电流源 + 固定电位点」网络，再由本模块统一求解，
不在任何一种电桥旁边另抄一套专用公式。

建模约定
--------
- 节点用字符串命名；电阻为 ``(节点a, 节点b, 阻值)``，阻值允许为 0——
  零欧电阻表示短接线，求解前用并查集把两端合并成一个超节点，
  不往电导矩阵里写 1/0。
- 电流源为 ``(节点a, 节点b, 电流)``：向 a 注入电流、从 b 流出。
- ``fixed_voltages`` 把节点钳在指定电位（如参考地 0 V、理想桥源端）。
  若两个电位不同的固定点被零欧电阻并到同一超节点，结构上矛盾，
  判为奇异并说明原因。

奇异性 / 病态性判定（本服务的取舍）
----------------------------------
采用**完全选主元（行列对称交换）的高斯消元**，电导矩阵是对称半正定阵，
对称选主元后各主元保持为正，且主元顺序天然按量级排列：

1. 某一步子矩阵最大元若不超过原始矩阵最大元的 ``PIVOT_ZERO``（1e-12），
   判为**结构奇异**（``circuit_singular``）——物理上对应存在与参考点
   没有电导连接的孤立节点组，或固定电位被短接强制成两个值；
2. 消元完成后取最大主元与最小主元之比（对称正定阵的廉价条件数估计），
   超过 ``COND_LIMIT``（1e12）判为**病态**（``circuit_ill_conditioned``），
   错误里带回实测比值与阈值，调用方可知拒绝原因。

选它而不是「先估计条件数再判定」的理由与代价写在 README「节点求解方案
的取舍」一节：消元与判定在同一遍扫描内完成、不额外解方程、也不引入
numpy；代价是主元比只是启发式阈值，对尺度悬殊的网络偏保守，会宁可不
算也不吐出有效数字丢失的结果。所有线性代数异常（除零、溢出、非数）
都在本模块内翻译成带原因的 :class:`NetworkError`，绝不向外透传。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: 主元小于原始矩阵最大元的该比例 → 结构奇异。
#: 取 1e-15：仅当电导小到相对矩阵最大元在双精度近零（真无连接/下溢）才判奇异；
#: 比这大但仍跨多个量级（1e-12..1e-15）的弱连接归入病态（见 COND_LIMIT）。
PIVOT_ZERO = 1e-15
_PIVOT_ZERO_TEXT = "1e-15"

#: 最大主元/最小主元超过该值 → 病态（有效数字估计不足约 12 位中的 4 位余量）
COND_LIMIT = 1e12


class NetworkError(ValueError):
    """网络无法得到可信数值解。``code`` 供机器判断，``message`` 说明原因。"""

    def __init__(self, code: str, message: str, **details: float) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        #: 诊断细节（如实测主元比），便于调用方记录与复核
        self.details = details


@dataclass(frozen=True)
class ResistiveNetwork:
    """线性电阻网络：电阻列表、电流源列表与固定电位点。"""

    resistors: Sequence[tuple[str, str, float]]
    current_sources: Sequence[tuple[str, str, float]] = ()
    fixed_voltages: Mapping[str, float] = frozenset()

    def __post_init__(self) -> None:
        # dataclass(frozen=True) 下用 object.__setattr__ 规整为内部容器
        object.__setattr__(self, "resistors", tuple(self.resistors))
        object.__setattr__(self, "current_sources", tuple(self.current_sources))
        object.__setattr__(self, "fixed_voltages", dict(self.fixed_voltages))


@dataclass(frozen=True)
class NodalSolution:
    """节点方程的解：原始节点名 -> 电位（伏）。"""

    voltages: Mapping[str, float]

    def voltage(self, node: str) -> float:
        return float(self.voltages[node])


class _UnionFind:
    def __init__(self, items: set[str]) -> None:
        self.parent = {x: x for x in items}

    def find(self, x: str) -> str:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # 路径压缩
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def solve(network: ResistiveNetwork) -> NodalSolution:
    """解节点方程，返回每个原始节点的电位。

    失败时抛 :class:`NetworkError`（``circuit_singular`` /
    ``circuit_ill_conditioned``），不会让除零、溢出或非数漏出本模块。
    """
    uf, fixed_group = _collect_components(network)

    # 给每个自由超节点编号；固定超节点直接取钳位电位
    free_groups: list[str] = []
    group_index: dict[str, int] = {}
    for node in uf.parent:
        root = uf.find(node)
        if root in fixed_group:
            continue
        if root not in group_index:
            group_index[root] = len(free_groups)
            free_groups.append(root)

    n = len(free_groups)
    g = [[0.0] * n for _ in range(n)]
    rhs = [0.0] * n
    g_max = 0.0

    def group_of(node: str) -> str:
        return uf.find(node)

    # 电阻盖章（零欧已在并查集中合并；同组内的非零电阻被短接，跳过）
    for a, b, r in network.resistors:
        if r < 0.0:
            raise NetworkError("circuit_singular", f"网络构造错误：出现负电阻 {r}")
        if r == 0.0:
            continue  # 零欧：已合并
        ga, gb = group_of(a), group_of(b)
        if ga == gb:
            continue
        conductance = 1.0 / r
        ia, ib = group_index.get(ga), group_index.get(gb)
        if ia is not None and ib is not None:
            g[ia][ia] += conductance
            g[ib][ib] += conductance
            g[ia][ib] -= conductance
            g[ib][ia] -= conductance
            g_max = max(g_max, conductance)
        elif ia is not None:
            rhs[ia] += conductance * fixed_group[gb]
            g[ia][ia] += conductance
            g_max = max(g_max, conductance)
        elif ib is not None:
            rhs[ib] += conductance * fixed_group[ga]
            g[ib][ib] += conductance
            g_max = max(g_max, conductance)
        # 两端都固定：电流由理想钳位源吸收，不进节点方程

    # 电流源盖章：向 a 注入、从 b 抽走
    for a, b, current in network.current_sources:
        ga, gb = group_of(a), group_of(b)
        ia, ib = group_index.get(ga), group_index.get(gb)
        if ia is not None:
            rhs[ia] += current
        if ib is not None:
            rhs[ib] -= current

    if n == 0:
        x: list[float] = []
        pivot_ratio = 1.0
    else:
        x, pivot_ratio = _gaussian_eliminate(g, rhs, g_max)
        for value in x:
            if value != value or value in (float("inf"), float("-inf")):
                raise NetworkError(
                    "circuit_ill_conditioned",
                    "节点方程的解含非数或无穷大：网络近奇异，结果不可信",
                    pivot_ratio=pivot_ratio,
                    cond_limit=COND_LIMIT,
                )

    voltages: dict[str, float] = {}
    for node in uf.parent:
        root = uf.find(node)
        if root in fixed_group:
            voltages[node] = fixed_group[root]
        else:
            voltages[node] = x[group_index[root]]
    return NodalSolution(voltages)


def _collect_components(
    network: ResistiveNetwork,
) -> tuple[_UnionFind, dict[str, float]]:
    """并查集合并零欧电阻，并校验固定电位冲突；返回 (并查集, 超节点电位)。"""
    nodes: set[str] = set()
    for a, b, _r in network.resistors:
        nodes.add(a)
        nodes.add(b)
    for a, b, _i in network.current_sources:
        nodes.add(a)
        nodes.add(b)
    nodes.update(network.fixed_voltages)

    uf = _UnionFind(nodes)
    for a, b, r in network.resistors:
        if r == 0.0:
            uf.union(a, b)

    fixed_group: dict[str, float] = {}
    for node, voltage in network.fixed_voltages.items():
        root = uf.find(node)
        if root in fixed_group and fixed_group[root] != voltage:
            raise NetworkError(
                "circuit_singular",
                "结构奇异：零欧短接把两个不同电位的固定点连成同一节点"
                f"（{fixed_group[root]:g} V 与 {voltage:g} V）",
            )
        fixed_group[root] = float(voltage)
    return uf, fixed_group


def _gaussian_eliminate(
    g: list[list[float]], rhs: list[float], g_max: float
) -> tuple[list[float], float]:
    """对称完全选主元高斯消元；返回 (解向量（按列置换顺序）, 主元量级比)。"""
    n = len(g)
    perm = list(range(n))  # 列交换对应的变量置换
    pivot_max = 0.0
    pivot_min = float("inf")

    for k in range(n):
        # 在尾部子矩阵中找量级最大的元（对称选主元：行列一起换）
        best = abs(g[k][k])
        pr = pc = k
        for i in range(k, n):
            for j in range(k, n):
                value = abs(g[i][j])
                if value > best:
                    best, pr, pc = value, i, j
        if best <= PIVOT_ZERO * g_max:
            raise NetworkError(
                "circuit_singular",
                "结构奇异：存在与参考点无电导连接的孤立节点组（或该组仅由零欧短接构成），"
                f"第 {k + 1} 个主元不超过矩阵最大元的 {_PIVOT_ZERO_TEXT}",
                pivot_zero=PIVOT_ZERO,
                matrix_max=g_max,
            )
        if pr != k:
            g[k], g[pr] = g[pr], g[k]
            rhs[k], rhs[pr] = rhs[pr], rhs[k]
        if pc != k:
            for i in range(n):
                g[i][k], g[i][pc] = g[i][pc], g[i][k]
            perm[k], perm[pc] = perm[pc], perm[k]

        pivot = g[k][k]
        pivot_max = max(pivot_max, abs(pivot))
        pivot_min = min(pivot_min, abs(pivot))

        for i in range(k + 1, n):
            factor = g[i][k] / pivot
            if factor == 0.0:
                continue
            g[i][k] = 0.0
            for j in range(k + 1, n):
                g[i][j] -= factor * g[k][j]
            rhs[i] -= factor * rhs[k]

    pivot_ratio = pivot_max / pivot_min
    if pivot_ratio > COND_LIMIT:
        raise NetworkError(
            "circuit_ill_conditioned",
            f"网络病态：消元主元量级比达 {pivot_ratio:.3e}（阈值 {COND_LIMIT:.0e}），"
            "不同支路电导相差过于悬殊，节点电位的有效数字不足以支撑毫欧级标定；"
            "请核对比例臂/接触电阻量级或清理异常取值",
            pivot_ratio=pivot_ratio,
            cond_limit=COND_LIMIT,
        )

    # 回代（解的顺序跟随列置换，最后还原到自然编号）
    x_permuted = [0.0] * n
    for i in range(n - 1, -1, -1):
        residual = rhs[i]
        for j in range(i + 1, n):
            residual -= g[i][j] * x_permuted[j]
        x_permuted[i] = residual / g[i][i]

    x = [0.0] * n
    for i in range(n):
        x[perm[i]] = x_permuted[i]
    return x, pivot_ratio


def port_voltage(
    network: ResistiveNetwork, positive: str, negative: str
) -> tuple[float, NodalSolution]:
    """解网络并返回 positive − negative 的电位差及完整解。"""
    solution = solve(network)
    return solution.voltage(positive) - solution.voltage(negative), solution


def equivalent_resistance(
    resistors: Sequence[tuple[str, str, float]],
    positive: str,
    negative: str,
    grounded_nodes: Sequence[str] = (),
) -> float:
    """无源电阻网络在 positive/negative 间的等效电阻（戴维南内阻）。

    独立源置零后的固定电位点通过 ``grounded_nodes`` 钳到 0 V（如理想
    电压源的两端短接为同地）。positive/negative 两个**测量端子都不
    钳位**——在其间注入 1 A 探针电流，端口电位差在数值上即等效电阻；
    只有把网络与参考地相连的节点才需要放进 ``grounded_nodes``。
    两端被零欧路径短接时返回 0；端口无直流通路（或整网无参考点）则判奇异。
    """
    fixed = {node: 0.0 for node in grounded_nodes}
    if not fixed:
        # 没有任何参考点时整网电位平移自由：借负极端作参考，不影响电位差
        fixed[negative] = 0.0
    probe = ResistiveNetwork(
        current_sources=((positive, negative, 1.0),),
        fixed_voltages=fixed,
        resistors=resistors,
    )
    solution = solve(probe)
    return solution.voltage(positive) - solution.voltage(negative)
