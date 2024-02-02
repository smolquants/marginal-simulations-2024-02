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
