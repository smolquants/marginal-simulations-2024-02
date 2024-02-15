from typing import List

from ape import project
from ape.api.accounts import AccountAPI
from ape.contracts import ContractInstance


def deploy_mock_univ3_pool(
    tokens: List[ContractInstance],
    fee: int,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Deploys the mock Uniswap V3 pool.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    [token0, token1] = tokens
    return project.MockUniswapV3Pool.deploy(token0.address, token1.address, fee, sender=acc)


def deploy_mock_mrglv1_pool(
    tokens: List[ContractInstance],
    maintenance: int,
    oracle: ContractInstance,
    acc: AccountAPI,
) -> ContractInstance:
    [token0, token1] = tokens
    mrglv1_core = project.dependencies['MarginalV1Core']['v1.0.0-rc.4']
    return mrglv1_core.MarginalV1Pool.deploy(
        acc.address,  # make acc factory address since irrelevant for runner
        token0.address,
        token1.address,
        maintenance,
        oracle.address,
        sender=acc,
    )
