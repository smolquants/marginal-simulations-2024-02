import os
import pandas as pd

from typing import ClassVar, List, Mapping, Optional

from ape import chain
from backtest_ape.utils import get_block_identifier
from pydantic import validator

from marginal_simulations_2024_02.runners.base import BaseMarginalV1Runner
from marginal_simulations_2024_02.constants import MINIMUM_LIQUIDITY
from marginal_simulations_2024_02.utils import get_mrglv1_amounts_for_liquidity


class MarginalV1LPRunner(BaseMarginalV1Runner):
    liquidity: int = 0  # initial liquidity deployed by runner
    utilization: float = 0  # = pool.liquidityLocked / pool.totalLiquidity
    skew: float = 0  # [-1, 1]: -1 is all utilization short, +1 is all long
    leverage: float = 1.1  # average leverage of positions on pool

    _backtester_name: ClassVar[str] = "MarginalV1LPBacktest"
    _position_ids: List[int] = []  # position IDs for outstanding positions on mrglv1 pool (only two of them)

    @validator("utilization")
    def utilization_between_zero_and_one(cls, v, **kwargs):
        if v < 0 or v > 1:
            raise ValueError("utilization must be between 0 and 1")

    @validator("skew")
    def skew_mag_less_than_one(cls, v, **kwargs):
        if abs(v) > 1:
            raise ValueError("skew must be between -1 and 1")

    def _calculate_position_liquidity_deltas(self) -> (int, int):
        """
        Calculates position liquidity deltas to take for
        zeroForOne = true and zeroForOne = false values.

        Skew given by:
            S = (a - b) / (a + b)

        Utilization given by:
            U = (a + b) / (a + b + pool.liquidity)

        where
            a + b = pool.liquidityLocked
            a = position.liquidityLocked (zeroForOne = true)
            b = position.liquidityLocked (zeroForOne = false)

        Returns:
            a (int): The liquidity delta for the zeroForOne = true position
            b (int): The liquidity delta for the zeroForOne = false position
        """
        mock_mrglv1_pool = self._mocks["mrglv1_pool"]
        liquidity = mock_mrglv1_pool.state().liquidity
        liquidity_locked = mock_mrglv1_pool.liquidityLocked()
        assert liquidity_locked == 0, "positions already exist on pool"

        liquidity_delta_01 = (liquidity * self.utilization * (1 + self.skew)) // 2
        liquidity_delta_10 = (liquidity * self.utilization * (1 - self.skew)) // 2
        return (liquidity_delta_01, liquidity_delta_10)

    def setup(self, mocking: bool = True):
        """
        Overrides setup to deploy the Marginal v1 LP backtester.

        Args:
            mocking (bool): Whether to deploy mocks.
        """
        super().setup(mocking=mocking)
        if not mocking:
            raise Exception("Only mocking supported")

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

    def set_mocks_state(self, state: Mapping):
        """
        Sets the state of mocks.

        Args:
            state (Mapping): The new state of mocks.
        """
        # update mock univ3 pool for state attrs
        mock_univ3_pool = self._mocks["pool"]
        mock_univ3_pool.setSlot0(state["slot0"])
        mock_univ3_pool.setLiquidity(state["liquidity"])
        mock_univ3_pool.setFeeGrowthGlobalX128(state["fee_growth_global0_x128"], state["fee_growth_global1_x128"])
        for i in range(2):
            mock_univ3_pool.pushObservation(*state[f"observation{i}"])

    def init_strategy(self):
        """
        Initializes the strategy being backtested through backtester contract
        at the given block.
        """
        mock_mrglv1_initializer = self._mocks["mrglv1_initializer"]
        mock_univ3_pool = self._mocks["univ3_pool"]
        mock_tokens = self._mocks["tokens"]
        ecosystem = chain.provider.network.ecosystem

        # mint the LP position via the mrglv1 initializer
        sqrt_price_x96_desired = mock_univ3_pool.slot0().sqrtPriceX96
        amount0_desired, amount1_desired = get_mrglv1_amounts_for_liquidity(
            sqrt_price_x96_desired,
            self.liquidity,
        )
        initialize_params = (
            mock_tokens[0],  # token0
            mock_tokens[1],  # token1
            self.maintenance,
            mock_univ3_pool.fee(),
            self.backtester.address,  # recipient
            sqrt_price_x96_desired,
            0,
            MINIMUM_LIQUIDITY**2,  # liquidity to burn
            2**255 - 1,
            2**255 - 1,
            amount0_desired,
            amount1_desired,
            0,
            0,
            2**256 - 1,
        )

        # execute through backtester
        self.backtester.execute(
            mock_mrglv1_initializer.address,
            ecosystem.encode_transaction(
                mock_mrglv1_initializer.address,
                mock_mrglv1_initializer.createAndInitializePoolIfNecessary.abis[0],
                initialize_params,
            ).data,
            0,
            sender=self.acc,
        )

    def update_strategy(self, number: int, state: Mapping):
        """
        Updates the strategy being backtested through backtester contract.

        NOTE: Passing means passive LP.

        Args:
            number (int): The block number.
            state (Mapping): The state of references at block number.
        """
        pass

    def record(self, path: str, number: int, state: Mapping, values: List[int]):
        """
        Records the value and possibly some state at the given block.

        Args:
            path (str): The path to the csv file to write the record to.
            number (int): The block number.
            state (Mapping): The state of references at block number.
            values (List[int]): The value of the backtester for the state.
        """
        data = {"number": number}
        for i, value in enumerate(values):
            data[f"values{i}"] = value

        data.update(
            {
                "sqrtPriceX96": state["slot0"].sqrtPriceX96,
                "liquidity": state["liquidity"],
                "feeGrowthGlobal0X128": state["fee_growth_global0_x128"],
                "feeGrowthGlobal1X128": state["fee_growth_global1_x128"],
                "observation0": state["observation0"],
                "observation1": state["observation1"],
            }
        )

        header = not os.path.exists(path)
        df = pd.DataFrame(data={k: [v] for k, v in data.items()})
        df.to_csv(path, index=False, mode="a", header=header)
