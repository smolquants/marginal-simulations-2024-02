// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.17;

import {MockUniswapV3Pool as UniswapV3Pool} from "@marginal/v1-periphery/contracts/test/mocks/MockUniswapV3Pool.sol";
import {Setter} from "@smolquants/backtest-ape/contracts/Setter.sol";

contract MockUniswapV3Pool is UniswapV3Pool, Setter {
    uint256 public feeGrowthGlobal0X128;
    uint256 public feeGrowthGlobal1X128;

    constructor(address tokenA, address tokenB, uint24 _fee) UniswapV3Pool(tokenA, tokenB, _fee) {}

    function setFeeGrowthGlobalX128(uint256 _feeGrowthGlobal0X128, uint256 _feeGrowthGlobal1X128) external {
        feeGrowthGlobal0X128 = _feeGrowthGlobal0X128;
        feeGrowthGlobal1X128 = _feeGrowthGlobal1X128;
    }
}
