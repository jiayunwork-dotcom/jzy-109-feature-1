"""通用电阻网络：元件登记、零电阻收缩、节点方程装配。

这是本服务所有正算（四臂惠斯通电桥、开尔文双电桥）共用的底子：
电路只由电阻、理想电压源（钳位节点电位）、理想电流源（节点电流注入）
和参考地描述，求解统一交给 :mod:`app.circuit.solver` 的选主元高斯消元。

约定：

- ``resistor(a, b, r)`` 登记一只严格为正的电阻（非正、非有限属构造错误，
  上游校验必须先行挡住）；
- ``short(a, b)`` 登记零电阻连接（轭线电阻或接触电阻取 0 的物理含义就是
  两端等电位），装配时用并查集把两端收缩成同一个节点，而不是往矩阵里
  塞 1/0 的无穷电导；
- ``fix_voltage(a, v)`` 把节点钳到固定电位（理想电压源/参考地）；
- ``inject(a, i)`` 向节点注入电流（理想电流源，流入为正）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.circuit.errors import NetworkEquationError


@dataclass(frozen=True)
class Edge:
    a: int
    b: int
    resistance: float


class Network:
    """逐步搭起来的电阻网络；节点按首次出现的名字分配内部编号。"""

    def __init__(self) -> None:
        self._names: list[str] = []
        self._index: dict[str, int] = {}
        self._parent: list[int] = []
        self._edges: list[Edge] = []
        self._fixed: dict[int, float] = {}
        self._inject: dict[int, float] = {}

    # ---- 元件登记 -------------------------------------------------------

    def node(self, name: str) -> int:
        idx = self._index.get(name)
        if idx is None:
            idx = len(self._names)
            self._index[name] = idx
            self._names.append(name)
            self._parent.append(idx)
        return idx

    def resistor(self, a: str, b: str, r: float) -> None:
        if not math.isfinite(r) or r <= 0.0:
            # 这是编程契约：用户输入的合法性由 validation 层在构造网络前保证。
            raise ValueError(f"电阻元件必须为正有限值，收到 {r!r}（{a}—{b}）")
        self._edges.append(Edge(self.node(a), self.node(b), float(r)))

    def short(self, a: str, b: str) -> None:
        """零电阻连接：在装配阶段收缩节点。"""
        self._union(self.node(a), self.node(b))

    def fix_voltage(self, a: str, voltage: float) -> None:
        if not math.isfinite(voltage):
            raise ValueError(f"钳位电位必须有限，收到 {voltage!r}（节点 {a}）")
        idx = self.node(a)
        old = self._fixed.get(idx)
        if old is not None and old != float(voltage):
            # 同一节点（含稍后收缩到一起的节点）被钳到两个不同电位：
            # 等价于理想电压源短接，结构上无解，按奇异处理。
            raise NetworkEquationError(
                "network_singular",
                f"节点 {a} 被钳位到 {voltage} 与 {old} 两个不同电位（理想电压源短接）",
            )
        self._fixed[idx] = float(voltage)

    def inject(self, a: str, amps: float) -> None:
        if not math.isfinite(amps):
            raise ValueError(f"注入电流必须有限，收到 {amps!r}（节点 {a}）")
        idx = self.node(a)
        self._inject[idx] = self._inject.get(idx, 0.0) + float(amps)

    @property
    def has_fixed_voltage(self) -> bool:
        """是否已有电位钳位点（独立源置零后的无源网据此判断是否需要补地）。"""
        return bool(self._fixed)

    # ---- 并查集 ---------------------------------------------------------

    def _find(self, x: int) -> int:
        parent = self._parent
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def _union(self, x: int, y: int) -> None:
        rx, ry = self._find(x), self._find(y)
        if rx != ry:
            # 让编号较小的根作代表，节点命名更稳定、错误信息可读。
            if rx < ry:
                self._parent[ry] = rx
            else:
                self._parent[rx] = ry

    # ---- 装配 -----------------------------------------------------------

    def assemble(self) -> "Assembled":
        """收缩零电阻边后，把网络装配成 G·V = I（只保留自由节点）。"""
        roots = {i: self._find(i) for i in range(len(self._names))}

        fixed_voltage: dict[int, float] = {}
        for idx, v in self._fixed.items():
            root = roots[idx]
            if root in fixed_voltage and fixed_voltage[root] != v:
                raise NetworkEquationError(
                    "network_singular",
                    f"被零电阻短接的两个节点被钳到不同电位（{v} 与 {fixed_voltage[root]}）",
                )
            fixed_voltage[root] = v

        injections: dict[int, float] = {}
        for idx, amps in self._inject.items():
            root = roots[idx]
            if root not in fixed_voltage:
                injections[root] = injections.get(root, 0.0) + amps

        free_roots = sorted(r for r in set(roots.values()) if r not in fixed_voltage)
        comp = {root: k for k, root in enumerate(free_roots)}
        n = len(free_roots)
        matrix = [[0.0] * n for _ in range(n)]
        rhs = [0.0] * n

        for edge in self._edges:
            ra, rb = roots[edge.a], roots[edge.b]
            if ra == rb:
                continue  # 自环（两端已收缩到一起）不参与方程
            g = 1.0 / edge.resistance
            fa, fb = ra in fixed_voltage, rb in fixed_voltage
            if fa and fb:
                continue  # 两个钳位节点之间的电阻不影响自由节点电位
            if fa or fb:
                fixed_root, free_root = (ra, rb) if fa else (rb, ra)
                k = comp[free_root]
                matrix[k][k] += g
                rhs[k] += g * fixed_voltage[fixed_root]
            else:
                i, j = comp[ra], comp[rb]
                matrix[i][i] += g
                matrix[j][j] += g
                matrix[i][j] -= g
                matrix[j][i] -= g

        for root, amps in injections.items():
            rhs[comp[root]] += amps

        # 每个自由分量取一个原始节点名作代表，供错误信息指名道姓。
        representatives = [""] * n
        for idx, name in enumerate(self._names):
            root = roots[idx]
            if root in comp:
                k = comp[root]
                cur = representatives[k]
                if not cur or name < cur:
                    representatives[k] = name

        return Assembled(
            matrix=matrix,
            rhs=rhs,
            representatives=representatives,
            node_voltage_root=lambda name: roots[self._index[name]],
            fixed_voltage=fixed_voltage,
            roots=roots,
        )


@dataclass(frozen=True)
class Assembled:
    matrix: list[list[float]]
    rhs: list[float]
    representatives: list[str]
    node_voltage_root: object
    fixed_voltage: dict[int, float]
    roots: dict[int, int]
