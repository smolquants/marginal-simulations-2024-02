import click
import os
import pandas as pd

from typing import ClassVar, List, Mapping, Optional

from ape import chain
from backtest_ape.utils import get_block_identifier
from pydantic import validator

from marginal_simulations_2024_02.runners.base import BaseMarginalV1Runner
from marginal_simulations_2024_02.constants import FEE_UNIT, MINIMUM_LIQUIDITY
from marginal_simulations_2024_02.utils import (
    get_mrglv1_amounts_for_liquidity,
    get_mrglv1_size_from_liquidity_delta,
    get_mrglv1_position_key,
)


class MarginalV1LPRunner(BaseMarginalV1Runner):
    liquidity: int = 0  # initial liquidity deployed by runner
    utilization: float = 0  # = pool.liquidityLocked / pool.totalLiquidity
    skew: float = 0  # [-1, 1]: -1 is all utilization short, +1 is all long
    leverage: float = 1.1  # average leverage of positions on pool
    blocks_held: int = 7200  # average number of blocks positions held
    sqrt_price_tol: float = 0.0025  # sqrt price diff above which should arb pools

    _backtester_name: ClassVar[str] = "MarginalV1LPBacktest"

    _token_ids: List[int] = [-1, -1]  # token IDs for outstanding positions on mrglv1 pool (only two of them)
    _blocks_settle: int = [-1, -1]  # future blocks to settle positions at
    _positions_liquidated_cumulative: List[int] = [0, 0]
    _positions_settled_cumulative: List[int] = [0, 0]
    _sizes_liquidated_cumulative: List[int] = [0, 0]
    _sizes_settled_cumulative: List[int] = [0, 0]
    _net_liquidity_liquidated_cumulative: List[int] = [
        0,
        0,
    ]  # (state_after.liquidity - state_before.liquidity) - position.liquidityLocked
    _net_liquidity_settled_cumulative: List[int] = [0, 0]
    _last_univ3_fee_growth_global_x128: List[int] = [-1, -1]

    @validator("leverage")
    def leverage_greater_than_one(cls, v, **kwargs):
        if v <= 1:
            raise ValueError("leverage must be greater than 1")

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
        total_liquidity = liquidity + liquidity_locked

        liquidity_delta_01 = (total_liquidity * self.utilization * (1 + self.skew)) // 2
        liquidity_delta_10 = (total_liquidity * self.utilization * (1 - self.skew)) // 2
        return (liquidity_delta_01, liquidity_delta_10)

    def _arb_pools(self):
        """
        Arbs price differences between Marginal v1 pool and Uniswap v3 pool
        if below tolerance.
        """
        mock_tokens = self._mocks["tokens"]
        mock_univ3_pool = self._mocks["univ3_pool"]
        mock_mrglv1_pool = self._mocks["mrglv1_pool"]
        mock_mrglv1_arbitrageur = self._mocks["mrglv1_arbitrageur"]
        ref_WETH9 = self._refs["WETH9"]

        univ3_sqrt_price_x96 = mock_univ3_pool.slot0().sqrtPriceX96
        mrglv1_sqrt_price_x96 = mock_mrglv1_pool.state().sqrtPriceX96
        rel_sqrt_price_diff = univ3_sqrt_price_x96 / mrglv1_sqrt_price_x96 - 1

        click.echo(f"Uniswap v3 sqrt price X96: {univ3_sqrt_price_x96}")
        click.echo(f"Marginal v1 sqrt price X96: {mrglv1_sqrt_price_x96}")
        click.echo(f"Relative difference in sqrt price X96 values: {rel_sqrt_price_diff}")

        if abs(rel_sqrt_price_diff) <= self.sqrt_price_tol:
            return

        token_out = ref_WETH9.address if ref_WETH9.address in mock_tokens else mock_tokens[1].address
        sweep_as_eth = ref_WETH9.address == token_out
        execute_params = (
            mock_tokens[0],
            mock_tokens[1],
            self.maintenance,
            mock_univ3_pool.address,
            self.acc.address,
            token_out,
            0,
            0,
            0,
            2**256 - 1,
            sweep_as_eth,
        )
        click.echo("Arbitraging Marginal v1 and Uniswap v3 pools ...")
        mock_mrglv1_arbitrageur.execute(execute_params, sender=self.acc)

    def _simulate_swaps(self, state: Mapping):
        """
        Simulates swaps on Marginal v1 pool based on fee growth on Uniswap v3 pool,
        scaled down with respect to differences in pool liquidity.

        Args:
            state (Mapping): The state of references at block
        """
        mock_tokens = self._mocks["tokens"]
        mock_mrglv1_pool = self._mocks["mrglv1_pool"]
        mock_mrglv1_router = self._mocks["mrglv1_router"]
        mock_univ3_pool = self._mocks["univ3_pool"]

        # net fee growth is cumulative fee amounts per unit of liquidity since last check
        net_univ3_fee_growth_global_x128 = [
            state["fee_growth_global0_x128"] - self._last_univ3_fee_growth_global_x128[0],
            state["fee_growth_global1_x128"] - self._last_univ3_fee_growth_global_x128[1],
        ]

        # to be conservative, take avg between fees0 and fees1 in 1 terms, then swap size back and forth to simulate
        net_univ3_fee_volumes = [
            (net_univ3_fee_growth_global_x128[0] * state["liquidity"]) // (1 << 128),
            (net_univ3_fee_growth_global_x128[1] * state["liquidity"]) // (1 << 128),
        ]
        price = (state["slot0"].sqrtPriceX96 ** 2) / (1 << 192)
        net_univ3_fee_volume1 = int((price * net_univ3_fee_volumes[0] + net_univ3_fee_volumes[1]) / 2)
        click.echo(f"Net Uniswap v3 fee volumes: {net_univ3_fee_volumes}")
        click.echo(f"Min Uniswap v3 fee volume in token1 terms: {net_univ3_fee_volume1}")

        # scale mrglv1 fee volumes by: mrglv1 fee volume = (mrgl v1 liquidity / uni v3 liquidity) * uni v3 fee volume
        # roughly given uniswap dashboard (TODO: examine historical data)
        mrglv1_state = mock_mrglv1_pool.state()
        mrglv1_fee = mock_mrglv1_pool.fee()
        net_mrglv1_fee_volume1 = (net_univ3_fee_volume1 * mrglv1_state.liquidity) // state["liquidity"]
        click.echo(f"Desired net Marginal v1 fee1 volumes: {net_mrglv1_fee_volume1}")

        # get size to generate that volume on one side of two swaps (1 => 0 then 0 => 1)
        click.echo(f"Marginal v1 state before swaps: {mrglv1_state}")
        amount1_in = (net_mrglv1_fee_volume1 * FEE_UNIT) // mrglv1_fee
        click.echo(f"Desired amount1 in to Marginal v1 pool for swaps: {amount1_in}")
        if amount1_in == 0:
            return

        swap_params = (
            mock_tokens[1],
            mock_tokens[0],
            self.maintenance,
            mock_univ3_pool.address,
            self.acc.address,
            2**256 - 1,
            amount1_in,
            0,
            0,
        )
        receipt = mock_mrglv1_router.exactInputSingle(swap_params, sender=self.acc)
        amount0_out = -receipt.decode_logs(mock_mrglv1_pool.Swap)[0].amount0
        click.echo(f"Swapped token1 amount in {amount1_in} for token0 amount out {amount0_out}.")

        # swap amount0 back (0 => 1)
        swap_params = (
            mock_tokens[0],
            mock_tokens[1],
            self.maintenance,
            mock_univ3_pool.address,
            self.acc.address,
            2**256 - 1,
            amount0_out,
            0,
            0,
        )
        receipt = mock_mrglv1_router.exactInputSingle(swap_params, sender=self.acc)
        amount1_out = -receipt.decode_logs(mock_mrglv1_pool.Swap)[0].amount1
        click.echo(f"Swapped token0 amount in {amount0_out} for token1 amount out {amount1_out}.")

        # check fee volume growth due to swaps
        mrglv1_state_after = mock_mrglv1_pool.state()
        click.echo(f"Marginal v1 state after swaps: {mrglv1_state_after}")
        liquidity_delta_fees = mrglv1_state_after.liquidity - mrglv1_state.liquidity
        click.echo(f"Liquidity gained from fee volume: {liquidity_delta_fees}")

        fees0_delta, fees1_delta = get_mrglv1_amounts_for_liquidity(
            mrglv1_state_after.sqrtPriceX96,
            liquidity_delta_fees,
        )
        click.echo(f"Amounts gained from fee volume: {[fees0_delta, fees1_delta]}")

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
        state["observation0"] = (
            timestamp - seconds_ago,
            tick_cumulatives[0],
            seconds_per_liquidity_cumulatives[0],
            True,
        )
        state["observation1"] = (timestamp, tick_cumulatives[1], seconds_per_liquidity_cumulatives[1], True)
        return state

    def init_mocks_state(self, number: int, state: Mapping):
        """
        Initializes the state of mocks.

        Args:
            number (int): The init block number.
            state (Mapping): The init state of mocks at block number.
        """
        mock_univ3_pool = self._mocks["univ3_pool"]
        mock_mrglv1_initializer = self._mocks["mrglv1_initializer"]
        mock_mrglv1_manager = self._mocks["mrglv1_manager"]
        mock_mrglv1_router = self._mocks["mrglv1_router"]
        mock_tokens = self._mocks["tokens"]
        ecosystem = chain.provider.network.ecosystem

        # set the current state of univ3 and mrglv1 pools
        self.set_mocks_state(state)

        # store latest uni v3 fee growth values for relative volume on mrgl v1 pools
        for i in range(2):
            self._last_univ3_fee_growth_global_x128[i] = state[f"fee_growth_global{i}_x128"]

        # mint tokens to near inf tokens to:
        #  - univ3 pool so swaps work
        #  - backtester to add liquidity to mrglv1 pool
        #  - self.acc to take out positions on mrglv1 pool
        mock_token_addresses = [[mock_token.address for mock_token in mock_tokens] for i in range(3)]
        targets = sum(mock_token_addresses, [])
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
                mock_mrglv1_initializer.address,
                2**256 - 1,
            ).data
            for i, mock_token in enumerate(mock_tokens)
        ]
        values = [0 for _ in range(6)]
        self.backtester.multicall(targets, datas, values, sender=self.acc)

        for mock_token in mock_tokens:
            mock_token.mint(self.acc.address, 2**128 - 1, sender=self.acc)
            mock_token.approve(mock_mrglv1_manager.address, 2**256 - 1, sender=self.acc)
            mock_token.approve(mock_mrglv1_router.address, 2**256 - 1, sender=self.acc)

        # mint the LP position via the mrglv1 initializer
        sqrt_price_x96_desired = state["slot0"].sqrtPriceX96
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

    def set_mocks_state(self, state: Mapping):
        """
        Sets the state of mocks.

        Args:
            state (Mapping): The new state of mocks.
        """
        # update mock univ3 pool for state attrs
        mock_univ3_pool = self._mocks["univ3_pool"]
        datas = [
            mock_univ3_pool.setSlot0.as_transaction(state["slot0"]).data,
            mock_univ3_pool.setLiquidity.as_transaction(state["liquidity"]).data,
            mock_univ3_pool.setFeeGrowthGlobalX128.as_transaction(
                state["fee_growth_global0_x128"], state["fee_growth_global1_x128"]
            ).data,
            mock_univ3_pool.pushObservation.as_transaction(*state["observation0"]).data,
            mock_univ3_pool.pushObservation.as_transaction(*state["observation1"]).data,
        ]
        mock_univ3_pool.calls(datas, sender=self.acc)

    def update_strategy(self, number: int, state: Mapping):
        """
        Updates the strategy being backtested through backtester contract.

        NOTE: Passing means passive LP.

        Args:
            number (int): The block number.
            state (Mapping): The state of references at block number.
        """
        mock_tokens = self._mocks["tokens"]
        mock_univ3_pool = self._mocks["univ3_pool"]
        mock_mrglv1_manager = self._mocks["mrglv1_manager"]
        mock_mrglv1_pool = self._mocks["mrglv1_pool"]

        # simulate swaps for fee volume on mrgl v1
        self._simulate_swaps(state)

        # arbitrage univ3 and mrglv1 pools to close price gap
        self._arb_pools()

        # liquidate or settle outstanding positions
        for i, token_id in enumerate(self._token_ids.copy()):
            if token_id == -1:
                # no position there
                continue

            # get position values
            position = mock_mrglv1_manager.positions(token_id)
            click.echo(f"Position status of tokenID {token_id}: {position}")

            # cache state before settling/liquidating to calculate net liquidity gained/lost by pool
            pposition = mock_mrglv1_pool.positions(
                get_mrglv1_position_key(mock_mrglv1_manager.address, position.positionId)
            )
            mrglv1_state_before = mock_mrglv1_pool.state()

            # liquidate position if not safe
            if not position.safe:
                click.echo(f"Liquidating position with tokenID {token_id} ...")

                # liquidate the position
                mock_mrglv1_pool.liquidate(
                    self.acc.address, mock_mrglv1_manager.address, position.positionId, sender=self.acc
                )

                # cache state after and calculate net liquidity gained/lost
                mrglv1_state_after = mock_mrglv1_pool.state()
                liquidity_returned = mrglv1_state_after.liquidity - mrglv1_state_before.liquidity
                net_liquidity = liquidity_returned - pposition.liquidityLocked
                click.secho(
                    f"Net liquidity gained by pool after liquidating: {net_liquidity}", blink=(net_liquidity < 0)
                )

                self._token_ids[i] = -1
                self._positions_liquidated_cumulative[i] += 1
                self._sizes_liquidated_cumulative[i] += position.size
                self._net_liquidity_liquidated_cumulative[i] += net_liquidity
            # otherwise settle position if enough blocks have passed
            elif number >= self._blocks_settle[i]:
                click.echo(f"Settling position with tokenID {token_id} ...")

                # settle the position
                burn_params = (
                    mock_tokens[0],
                    mock_tokens[1],
                    self.maintenance,
                    mock_univ3_pool.address,
                    token_id,
                    self.acc.address,
                    2**256 - 1,
                )
                mock_mrglv1_manager.burn(burn_params, sender=self.acc)

                # cache state after and calculate net liquidity gained/lost
                mrglv1_state_after = mock_mrglv1_pool.state()
                liquidity_returned = mrglv1_state_after.liquidity - mrglv1_state_before.liquidity
                net_liquidity = liquidity_returned - pposition.liquidityLocked
                click.secho(f"Net liquidity gained by pool after settling: {net_liquidity}", blink=(net_liquidity < 0))

                self._token_ids[i] = -1
                self._positions_settled_cumulative[i] += 1
                self._sizes_settled_cumulative[i] += position.size
                self._net_liquidity_settled_cumulative[i] += net_liquidity

        # open any new positions if don't have existing long or short
        for i, token_id in enumerate(self._token_ids.copy()):
            if token_id != -1:
                # position already there
                continue

            liquidity_delta = self._calculate_position_liquidity_deltas()[i]
            mrglv1_state = mock_mrglv1_pool.state()
            zero_for_one = i == 0
            size_desired = get_mrglv1_size_from_liquidity_delta(
                mrglv1_state.liquidity,
                mrglv1_state.sqrtPriceX96,
                liquidity_delta,
                zero_for_one,
                self.maintenance,
            )
            margin = size_desired / (self.leverage - 1)
            mint_params = (
                mock_tokens[0],
                mock_tokens[1],
                self.maintenance,
                mock_univ3_pool.address,
                zero_for_one,
                size_desired,
                0,
                0,
                0,
                0,
                margin,
                self.acc.address,
                2**256 - 1,
            )
            receipt = mock_mrglv1_manager.mint(mint_params, sender=self.acc, value=int(1e18))  # excess ETH in case
            next_token_id = receipt.decode_logs(mock_mrglv1_manager.Mint)[0].tokenId
            next_position = mock_mrglv1_manager.positions(next_token_id)

            self._token_ids[i] = next_token_id
            self._blocks_settle[i] = number + self.blocks_held
            click.echo(f"Opened new position with tokenID {next_token_id}: {next_position}")

        # arb pools again given potential positions opened if arb there
        self._arb_pools()

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
                "univ3_sqrtPriceX96": state["slot0"].sqrtPriceX96,
                "univ3_liquidity": state["liquidity"],
                "univ3_feeGrowthGlobal0X128": state["fee_growth_global0_x128"],
                "univ3_feeGrowthGlobal1X128": state["fee_growth_global1_x128"],
                "univ3_observation0": state["observation0"],
                "univ3_observation1": state["observation1"],
            }
        )

        # all lists so unfold
        attr_names = [
            "_token_ids",
            "_positions_liquidated_cumulative",
            "_positions_settled_cumulative",
            "_sizes_liquidated_cumulative",
            "_sizes_settled_cumulative",
            "_net_liquidity_liquidated_cumulative",
            "_net_liquidity_settled_cumulative",
        ]
        for name in attr_names:
            cum_list = getattr(self, name)
            for i, cum_val in enumerate(cum_list):
                data[f"{name}{i}"] = cum_val

        header = not os.path.exists(path)
        df = pd.DataFrame(data={k: [v] for k, v in data.items()})
        df.to_csv(path, index=False, mode="a", header=header)
