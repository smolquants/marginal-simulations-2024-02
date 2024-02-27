# marginal-simulations-2024-02

Economic simulations for [Marginal](https://marginal.network).

## Replication

To check the results, clone the repo

```sh
git clone https://github.com/smolquants/marginal-simulations-2024-02.git
```

Install dependencies with [`hatch`](https://github.com/pypa/hatch) and [`ape`](https://github.com/ApeWorX/ape)

```sh
hatch build
hatch shell
(marginal-simulations-2024-02) ape plugins install .
```

Setup your environment with an [Alchemy](https://www.alchemy.com) key

```sh
export WEB3_ALCHEMY_PROJECT_ID=<YOUR_PROJECT_ID>
```

Then launch [`ape-notebook`](https://github.com/ApeWorX/ape-notebook)

```sh
(marginal-simulations-2024-02) ape notebook
```

## Scripts

Scripts using backtester contracts rely on [`backtest-ape`](https://github.com/smolquants/backtest-ape) and
[`ape-foundry`](https://github.com/ApeWorX/ape-foundry) mainnet-fork functionality. These produce backtest results
for passive liquidity in Marginal v1 pools.

Compile the needed contracts

```sh
(marginal-simulations-2024-02) ape compile --size
```

Then run the backtest script with e.g. the `MarginalV1LPRunner`

```sh
(marginal-simulations-2024-02) ape run backtester
INFO: Starting 'anvil' process.
You are connected to provider network ethereum:mainnet-fork:foundry.
Runner type (MarginalV1LPRunner): MarginalV1LPRunner
Runner kwarg (ref_addrs) [{}]: {"WETH9": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "univ3_pool": "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640", "univ3_static_quoter": "0xc80f61d1bdAbD8f5285117e1558fDDf8C64870FE"}
Runner kwarg (acc_addr) defaults to None. Do you want to input a value? [y/N]: N
Runner kwarg (maintenance) [250000]:
Runner kwarg (liquidity) [0]: 91287092917527680
Runner kwarg (utilization) [0]: 0.25
Runner kwarg (skew) [0]: -0.5
Runner kwarg (blocks_held) [7200]: 50400
Runner kwarg (sqrt_price_tol) [0.0025]:
Input leverage or buffer above safe margin minimum? (leverage, rel_margin_above_safe_min): leverage
leverage: 3.0
Runner instance: ref_addrs={'WETH9': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 'univ3_pool': '0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640', 'univ3_static_quoter': '0xc80f61d1bdAbD8f5285117e1558fDDf8C64870FE'} acc_addr=None maintenance=250000 liquidity=91287092917527680 utilization=0.25 skew=-0.5 leverage=3.0 rel_margin_above_safe_min=0 blocks_held=50400 sqrt_price_tol=0.0025
Start block number: 17998181
Stop block number [-1]: 19311400
Step size [1]: 2400
Setting up runner ...
Deploying mock ERC20 tokens ...
```
