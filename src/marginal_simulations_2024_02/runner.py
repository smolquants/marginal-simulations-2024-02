from typing import Any, ClassVar, List
from ape import Contract

from backtest_ape.base import BaseRunner


class MarginalV1LPRunner(BaseRunner):
    liquidity: int = 0  # liquidity contribution to Marginal pool by LP

    _ref_keys: ClassVar[List[str]] = ["univ3_pool"]

    def __init__(self, **data: Any):
        """
        Overrides BaseRunner init to also store ape Contract instances
        for tokens in ref pool.
        """
        super().__init__(**data)

        # store token contracts in _refs
        univ3_pool = self._refs["univ3_pool"]
        self._refs["tokens"] = [Contract(univ3_pool.token0()), Contract(univ3_pool.token1())]
