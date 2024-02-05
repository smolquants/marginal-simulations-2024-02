// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.17;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import {IUniswapV3SwapCallback} from "@uniswap/v3-core/contracts/interfaces/callback/IUniswapV3SwapCallback.sol";
import {IUniswapV3Pool} from "@uniswap/v3-core/contracts/interfaces/IUniswapV3Pool.sol";

import {TestMarginalV1PoolCallee} from "@marginal/v1-periphery/contracts/test/TestMarginalV1PoolCallee.sol";

/// @dev Adds Uniswap v3 swap callback handler to test Marginal v1 pool callee
contract Callee is IUniswapV3SwapCallback, TestMarginalV1PoolCallee {
    using SafeERC20 for IERC20;

    event UniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, address sender);
    event UniswapV3SwapReturn(int256 amount0, int256 amount1);

    function uniswapV3Swap(
        address pool,
        address recipient,
        bool zeroForOne,
        int256 amountSpecified,
        uint160 sqrtPriceLimitX96
    ) external returns (int256 amount0, int256 amount1) {
        (amount0, amount1) = IUniswapV3Pool(pool).swap(
            recipient,
            zeroForOne,
            amountSpecified,
            sqrtPriceLimitX96,
            abi.encode(msg.sender)
        );
        emit UniswapV3SwapReturn(amount0, amount1);
    }

    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data) external virtual {
        address sender = abi.decode(data, (address));

        emit UniswapV3SwapCallback(amount0Delta, amount1Delta, sender);

        if (amount0Delta > 0) {
            address token0 = IUniswapV3Pool(msg.sender).token0();
            IERC20(token0).safeTransferFrom(sender, msg.sender, uint256(amount0Delta));
        } else if (amount1Delta > 0) {
            address token1 = IUniswapV3Pool(msg.sender).token1();
            IERC20(token1).safeTransferFrom(sender, msg.sender, uint256(amount1Delta));
        } else {
            assert(amount0Delta == 0 && amount1Delta == 0);
        }
    }
}
