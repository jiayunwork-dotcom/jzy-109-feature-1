"""电路求解层的异常类型（独立于 network/solver，避免循环导入）。"""
from __future__ import annotations


class NetworkEquationError(ValueError):
    """节点方程不可靠求解。

    code ∈ {"network_singular", "network_ill_conditioned"}：
    ``network_singular`` 表示方程无解/解不唯一（悬空节点、钳位矛盾等结构性
    问题）；``network_ill_conditioned`` 表示方程近奇异，双精度消元已不能给
    出可信数字（条件数越界、上溢或残差超限）。``message`` 面向操作人员，
    说明具体原因，绝不为线性代数异常、无穷大或 NaN。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
