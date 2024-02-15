from typing import ClassVar

from marginal_simulations_2024_02.runners.base import BaseMarginalV1Runner


class MarginalV1LPRunner(BaseMarginalV1Runner):
    liquidity: int = 0
    _backtester_name: ClassVar[str] = "MarginalV1LPBacktest"

    def setup(self, mocking: bool = True):
        """
        Overrides setup to deploy the Marginal v1 LP backtester.

        Args:
            mocking (bool): Whether to deploy mocks.
        """
        super().setup(mocking=mocking)
        if not mocking:
            return

        # deploy the backtester
        pool_addr = self._mocks["mrglv1_pool"].address
        self.deploy_strategy(*[pool_addr])
        self._initialized = True
