from eth_abi.packed import encode_packed
from eth_utils import keccak

from math import sqrt

from marginal_simulations_2024_02.constants import MAINTENANCE_UNIT


# common
def get_sqrt_ratio_at_tick(tick: int) -> int:
    return int(((1.0001 ** (tick)) ** (1 / 2)) * (1 << 96))


# mrgl v1 utility functions
def get_mrglv1_position_key(address: str, id: int) -> bytes:
    return keccak(encode_packed(["address", "uint96"], [address, id]))


def get_mrglv1_amounts_for_liquidity(sqrt_price_x96: int, liquidity: int) -> (int, int):
    amount0 = (liquidity << 96) // sqrt_price_x96
    amount1 = (liquidity * sqrt_price_x96) // (1 << 96)
    return (amount0, amount1)


def get_mrglv1_sqrt_price_x96_next_open(
    liquidity: int,
    sqrt_price_x96: int,
    liquidity_delta: int,
    zero_for_one: bool,
    maintenance: int,
) -> int:
    prod = (liquidity_delta * (liquidity - liquidity_delta) * MAINTENANCE_UNIT) // (MAINTENANCE_UNIT + maintenance)
    under = liquidity**2 - 4 * prod
    root = int(sqrt(under))

    sqrt_price_x96_next = (
        int(sqrt_price_x96 * (liquidity + root)) // (2 * (liquidity - liquidity_delta))
        if not zero_for_one
        else int(sqrt_price_x96 * 2 * (liquidity - liquidity_delta)) // (liquidity + root)
    )

    return sqrt_price_x96_next


def get_mrglv1_insurances(
    liquidity: int,
    sqrt_price_x96: int,
    sqrt_price_x96_next: int,
    liquidity_delta: int,
    zero_for_one: bool,
) -> (int, int):
    prod = (
        ((liquidity - liquidity_delta) * sqrt_price_x96_next) // sqrt_price_x96
        if not zero_for_one
        else ((liquidity - liquidity_delta) * sqrt_price_x96) // sqrt_price_x96_next
    )
    insurance0 = ((liquidity - prod) << 96) // sqrt_price_x96
    insurance1 = ((liquidity - prod) * sqrt_price_x96) // (1 << 96)
    return (insurance0, insurance1)


def get_mrglv1_debts(
    sqrt_price_x96_next: int,
    liquidity_delta: int,
    insurance0: int,
    insurance1: int,
) -> (int, int):
    debt0 = (liquidity_delta << 96) // sqrt_price_x96_next - insurance0
    debt1 = (liquidity_delta * sqrt_price_x96_next) // (1 << 96) - insurance1
    return (debt0, debt1)


def get_mrglv1_size_from_liquidity_delta(
    liquidity: int,
    sqrt_price_x96: int,
    liquidity_delta: int,
    zero_for_one: bool,
    maintenance: int,
) -> int:
    # sx = dy / sqrt(P * P') for zero_for_one = False
    # sy = dx * sqrt(P * P') for zero_for_one = True
    sqrt_price_x96_next = get_mrglv1_sqrt_price_x96_next_open(
        liquidity,
        sqrt_price_x96,
        liquidity_delta,
        zero_for_one,
        maintenance,
    )
    insurance0, insurance1 = get_mrglv1_insurances(
        liquidity,
        sqrt_price_x96,
        sqrt_price_x96_next,
        liquidity_delta,
        zero_for_one,
    )
    debt0, debt1 = get_mrglv1_debts(
        sqrt_price_x96_next,
        liquidity_delta,
        insurance0,
        insurance1,
    )
    size = (
        (debt1 * (1 << 192)) // (sqrt_price_x96_next * sqrt_price_x96)
        if zero_for_one
        else (debt0 * (sqrt_price_x96_next * sqrt_price_x96)) // (1 << 192)
    )
    return size


# uni v3 utility functions
def get_univ3_amount0_for_liquidity(sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, liquidity: int) -> int:
    return (((liquidity * (1 << 96)) * (sqrt_ratio_b_x96 - sqrt_ratio_a_x96)) // sqrt_ratio_b_x96) // sqrt_ratio_a_x96


def get_univ3_amount1_for_liquidity(sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, liquidity: int) -> int:
    return (liquidity * (sqrt_ratio_b_x96 - sqrt_ratio_a_x96)) // (1 << 96)


def get_univ3_amounts_for_liquidity(
    sqrt_ratio_x96: int, sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, liquidity: int
) -> (int, int):
    # @dev only implemented for tick_lower <= state.tick <= tick_upper
    assert sqrt_ratio_a_x96 <= sqrt_ratio_x96 and sqrt_ratio_x96 <= sqrt_ratio_b_x96
    amount0 = get_univ3_amount0_for_liquidity(sqrt_ratio_x96, sqrt_ratio_b_x96, liquidity)
    amount1 = get_univ3_amount1_for_liquidity(sqrt_ratio_a_x96, sqrt_ratio_x96, liquidity)
    return (amount0, amount1)


def get_univ3_liquidity_for_amount0(sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, amount0: int) -> int:
    intermediate = (sqrt_ratio_a_x96 * sqrt_ratio_b_x96) // (1 << 96)
    return (amount0 * intermediate) // (sqrt_ratio_b_x96 - sqrt_ratio_a_x96)


def get_univ3_liquidity_for_amount1(sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, amount1: int) -> int:
    return (amount1 * (1 << 96)) // (sqrt_ratio_b_x96 - sqrt_ratio_a_x96)


def get_univ3_liquidity_for_amounts(
    sqrt_ratio_x96: int, sqrt_ratio_a_x96: int, sqrt_ratio_b_x96: int, amount0: int, amount1: int
) -> int:
    # @dev only implemented for tick_lower <= state.tick <= tick_upper
    assert sqrt_ratio_a_x96 <= sqrt_ratio_x96 and sqrt_ratio_x96 <= sqrt_ratio_b_x96
    liquidity0 = get_univ3_liquidity_for_amount0(sqrt_ratio_x96, sqrt_ratio_b_x96, amount0)
    liquidity1 = get_univ3_liquidity_for_amount1(sqrt_ratio_a_x96, sqrt_ratio_x96, amount1)
    return liquidity0 if liquidity0 < liquidity1 else liquidity1
