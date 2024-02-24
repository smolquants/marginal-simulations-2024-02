// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

import {IMarginalV1Pool} from "@marginal/v1-core/contracts/interfaces/IMarginalV1Pool.sol";
import {LiquidityMath} from "@marginal/v1-core/contracts/libraries/LiquidityMath.sol";

import {Backtest} from "@smolquants/backtest-ape/contracts/Backtest.sol";

/// @title Marginal V1 Liquidity Provider Backtester
/// @notice Backtests a hypothetical LP position on Marginal V1
contract MarginalV1LPBacktest is Backtest {
    address public pool;

    constructor(address _pool) {
        pool = _pool;
    }

    /// @notice The LP shares held by this contract for pool
    function sharesLp() public view returns (uint256) {
        return IERC20(pool).balanceOf(address(this));
    }

    /// @notice The total LP shares distributed by the pool
    function totalShares() public view returns (uint256) {
        return IERC20(pool).totalSupply();
    }

    /// @notice Liquidity credited to LP for their shares in pool
    /// @param totalLiquidity Pool state liquidity plus liquidity locked
    /// @return liquidity_ The liquidity contribution to pool for shares held by this contract
    function liquidityLp(uint128 totalLiquidity) public view returns (uint128 liquidity_) {
        uint256 _shares = sharesLp();
        require(_shares > 0, "backtest holds zero LP shares");
        liquidity_ = uint128(Math.mulDiv(totalLiquidity, _shares, totalShares()));
    }

    /// @notice Reports the current liquidity and associated token0 and token1 amounts for LP shares held
    /// @return values_ The current LP held liquidity and token0, token1 amounts in addition to the pool sqrtPriceX96
    function values() public view virtual override returns (uint256[] memory values_) {
        values_ = new uint256[](4);
        (
            uint160 sqrtPriceX96, // pool state sqrt price
            ,
            uint128 liquidity, // pool state liquidity
            ,
            ,
            ,
            ,
            bool initialized
        ) = IMarginalV1Pool(pool).state();
        require(initialized, "pool not initialized");
        uint128 liquidityLocked = IMarginalV1Pool(pool).liquidityLocked();

        uint128 totalLiquidity = liquidity + liquidityLocked;
        uint128 _liquidity = liquidityLp(totalLiquidity);

        (uint256 amount0, uint256 amount1) = LiquidityMath.toAmounts(_liquidity, sqrtPriceX96);

        // set the values to track through backtest
        values_[0] = uint256(_liquidity);
        values_[1] = uint256(sqrtPriceX96);
        values_[2] = amount0;
        values_[3] = amount1;
    }
}
