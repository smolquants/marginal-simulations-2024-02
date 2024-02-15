// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.17;

import {MockUniswapV3Pool} from "./MockUniswapV3Pool.sol";

contract MockUniswapV3Factory {
    mapping(address => mapping(address => mapping(uint24 => address))) public getPool;

    /// @dev See IUniswapV3Factory
    function createPool(address tokenA, address tokenB, uint24 fee) external returns (address pool) {
        require(tokenA != tokenB);
        (address token0, address token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        require(token0 != address(0));
        require(getPool[token0][token1][fee] == address(0));
        pool = address(new MockUniswapV3Pool(token0, token1, fee));
        getPool[token0][token1][fee] = pool;
        // populate mapping in the reverse direction, deliberate choice to avoid the cost of comparing addresses
        getPool[token1][token0][fee] = pool;
    }
}
