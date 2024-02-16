from typing import ClassVar, Mapping, Optional

from ape import chain
from backtest_ape.utils import get_block_identifier

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

    def get_refs_state(self, number: Optional[int] = None) -> Mapping:
        """
        Gets the state of references at given block.

        Args:
            number (int): The block number. If None, then last block
                from current provider chain.

        Returns:
            Mapping: The state of references at block.
        """
        block_identifier = get_block_identifier(number)
        ref_univ3_pool = self._refs["univ3_pool"]
        seconds_ago = self._mocks["mrglv1_pool"].secondsAgo()
        state = {}

        state["slot0"] = ref_univ3_pool.slot0(block_identifier=block_identifier)
        state["liquidity"] = ref_univ3_pool.liquidity(block_identifier=block_identifier)
        state["fee_growth_global0_x128"] = ref_univ3_pool.feeGrowthGlobal0X128(block_identifier=block_identifier)
        state["fee_growth_global1_x128"] = ref_univ3_pool.feeGrowthGlobal1X128(block_identifier=block_identifier)

        # build associated observations array
        timestamp = chain.blocks[block_identifier].timestamp
        tick_cumulatives, seconds_per_liquidity_cumulatives = ref_univ3_pool.observe(
            [seconds_ago, 0], block_identifier=block_identifier
        )
        state["observations0"] = (
            timestamp - seconds_ago,
            tick_cumulatives[0],
            seconds_per_liquidity_cumulatives[0],
            True,
        )
        state["observations1"] = (timestamp, tick_cumulatives[1], seconds_per_liquidity_cumulatives[1], True)
        return state

    def init_mocks_state(self, number: int, state: Mapping):
        """
        Initializes the state of mocks.

        Args:
            number (int): The init block number.
            state (Mapping): The init state of mocks at block number.
        """
        mock_univ3_pool = self._mocks["univ3_pool"]
        mock_tokens = self._mocks["tokens"]
        ecosystem = chain.provider.network.ecosystem

        # set the current state of univ3 and mrglv1 pools
        self.set_mocks_state(state)

        # mint tokens to near inf tokens to univ3 pool so swaps work
        # and to backtester to add liquidity to mrglv1 pool
        targets = [mock_token.address for mock_token in mock_tokens]
        targets += targets  # given 3 iterations to multicall
        targets += targets
        datas = [
            ecosystem.encode_transaction(
                mock_token.address,
                mock_token.mint.abis[0],
                self.backtester.address,
                2**128 - 1,
            ).data
            for i, mock_token in enumerate(mock_tokens)
        ]
        datas += [
            ecosystem.encode_transaction(
                mock_token.address,
                mock_token.mint.abis[0],
                mock_univ3_pool.address,
                2**128 - 1,
            ).data
            for i, mock_token in enumerate(mock_tokens)
        ]
        datas += [
            ecosystem.encode_transaction(
                mock_token.address,
                mock_token.approve.abis[0],
                mock_univ3_pool.address,
                2**256 - 1,
            ).data
            for i, mock_token in enumerate(mock_tokens)
        ]
        values = [0 for _ in range(6)]
        self.backtester.multicall(targets, datas, values, sender=self.acc)
