from typing import Any, ClassVar, List

import click
from ape import Contract

from backtest_ape.base import BaseRunner
from backtest_ape.setup import deploy_mock_erc20

from marginal_simulations_2024_02.runners.setup import (
    deploy_mock_univ3_factory,
    create_mock_univ3_pool,
    deploy_mock_mrglv1_factory,
    create_mock_mrglv1_pool,
)


class BaseMarginalV1Runner(BaseRunner):
    maintenance: int = 250000  # min maintenance of the Marginal pool used in backtests

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

    def setup(self, mocking: bool = True):
        """
        Sets up the Marginal V1 LP runner for testing. If mocking, deploys mock ERC20 tokens
        needed for pool, mock Uniswap V3 reference oracle pool, and mock Marginal V1 pool.

        Args:
            mocking (bool): Whether to deploy mocks.
        """
        if mocking:
            self.deploy_mocks()

    def deploy_mocks(self):
        """
        Deploys the mock contracts.
        """
        # deploy the mock erc20s
        click.echo("Deploying mock ERC20 tokens ...")
        mock_tokens = [
            deploy_mock_erc20(f"Mock Token{i}", token.symbol(), token.decimals(), self.acc)
            for i, token in enumerate(self._refs["tokens"])
        ]

        # deploy the mock univ3 factory and pool
        ref_univ3_pool = self._refs["univ3_pool"]
        fee = ref_univ3_pool.fee()
        mock_univ3_factory = deploy_mock_univ3_factory(self.acc)
        mock_univ3_pool = create_mock_univ3_pool(mock_univ3_factory, mock_tokens, fee, self.acc)

        # deploy the mock mrglv1 factory and pool
        mock_mrglv1_factory = deploy_mock_mrglv1_factory(
            mock_univ3_factory,
            0,  # cardinality min not relevant for backtests
            self.acc,
        )
        mock_mrglv1_pool = create_mock_mrglv1_pool(
            mock_mrglv1_factory, mock_tokens, self.maintenance, mock_univ3_pool, self.acc
        )

        self._mocks = {
            "tokens": mock_tokens,
            "univ3_factory": mock_univ3_factory,
            "univ3_pool": mock_univ3_pool,
            "mrglv1_factory": mock_mrglv1_factory,
            "mrglv1_pool": mock_mrglv1_pool,
        }
