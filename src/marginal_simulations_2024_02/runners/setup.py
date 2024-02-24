from typing import List

from ape import project
from ape.api.accounts import AccountAPI
from ape.contracts import ContractInstance


def deploy_mock_univ3_factory(acc: AccountAPI) -> ContractInstance:
    """
    Deploys the mock Uniswap V3 factory.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    return project.MockUniswapV3Factory.deploy(sender=acc)


def create_mock_univ3_pool(
    univ3_factory: ContractInstance,
    tokens: List[ContractInstance],
    fee: int,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Creates the mock Uniswap V3 pool.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    [token0, token1] = tokens

    univ3_factory.createPool(token0.address, token1.address, fee, sender=acc)
    univ3_pool_addr = univ3_factory.getPool(token0.address, token1.address, fee)
    univ3_pool = project.MockUniswapV3Pool.at(univ3_pool_addr)
    return univ3_pool


def deploy_mock_mrglv1_factory(
    univ3_factory: ContractInstance,
    obs_cardinality_min: int,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Deploys the mock Marginal V1 factory.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    deployer = project.MarginalV1PoolDeployer.deploy(sender=acc)
    return project.MarginalV1Factory.deploy(deployer.address, univ3_factory.address, obs_cardinality_min, sender=acc)


def create_mock_mrglv1_pool(
    factory: ContractInstance,
    tokens: List[ContractInstance],
    maintenance: int,
    oracle: ContractInstance,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Creates the mock Marginal V1 Pool.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    [token0, token1] = tokens
    univ3_fee = oracle.fee()

    factory.createPool(token0.address, token1.address, maintenance, univ3_fee, sender=acc)
    pool_addr = factory.getPool(token0.address, token1.address, maintenance, oracle.address)
    pool = project.MarginalV1Pool.at(pool_addr)
    return pool


def deploy_mock_mrglv1_initializer(
    factory: ContractInstance,
    WETH9: ContractInstance,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Deploys the mock Marginal V1 pool initializer.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    return project.PoolInitializer.deploy(factory.address, WETH9.address, sender=acc)


def deploy_mock_mrglv1_router(
    factory: ContractInstance,
    WETH9: ContractInstance,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Deploys the mock Marginal V1 pool initializer.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    return project.Router.deploy(factory.address, WETH9.address, sender=acc)


def deploy_mock_mrglv1_manager(
    factory: ContractInstance,
    WETH9: ContractInstance,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Deploys the mock Marginal V1 NFT position manager.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    return project.NonfungiblePositionManager.deploy(factory.address, WETH9.address, sender=acc)


def deploy_mock_mrglv1_arbitrageur(
    factory: ContractInstance,
    WETH9: ContractInstance,
    acc: AccountAPI,
) -> ContractInstance:
    """
    Deploys the mock Marginal V1 pair arbitrageur.

    Returns:
        :class:`ape.contracts.ContractInstance`
    """
    return project.PairArbitrageur.deploy(factory.address, WETH9.address, sender=acc)
