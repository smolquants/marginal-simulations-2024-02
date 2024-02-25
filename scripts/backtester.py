import click
import os
import marginal_simulations_2024_02

from ast import literal_eval
from ape import networks
from typing_inspect import get_origin


def main():
    """
    Main backtester script.
    """
    # echo provider setup
    ecosystem_name = networks.provider.network.ecosystem.name
    network_name = networks.provider.network.name
    provider_name = networks.provider.name
    connection_name = f"{ecosystem_name}:{network_name}:{provider_name}"
    click.echo(f"You are connected to provider network {connection_name}.")

    # fail if not mainnet-fork
    if network_name != "mainnet-fork":
        raise ValueError("not connected to mainnet-fork.")

    # prompt user which backtest runner to use
    runner_cls_name = click.prompt(
        "Runner type", type=click.Choice(marginal_simulations_2024_02.__all__, case_sensitive=False)
    )
    runner_cls = getattr(marginal_simulations_2024_02, runner_cls_name)

    # prompt user for fields on runner to init with
    skip_names = []
    kwargs = {}
    for name, field in runner_cls.__fields__.items():
        if name in skip_names:
            continue

        # default to str if not base type
        type_origin = get_origin(field.annotation)
        type_ = field.annotation if type_origin is None else str

        # confirm prompt if Optional
        if field.default is None:
            if not click.confirm(f"Runner kwarg ({name}) defaults to None. Do you want to input a value?"):
                kwargs[name] = field.default
                continue

        value = click.prompt(f"Runner kwarg ({name})", default=field.default, type=type_)

        # parse field value from str if not base type
        if type_origin is not None:
            value = literal_eval(value)

        kwargs[name] = value

    # setup runner
    runner = runner_cls(**kwargs)
    click.echo(f"Runner instance: {runner}")

    # run backtest
    univ3_pool_addr = runner._refs["univ3_pool"].address
    start = click.prompt("Start block number", type=int)
    stop = click.prompt("Stop block number", type=int, default=-1)
    step = click.prompt("Step size", type=int, default=1)

    # remove file if already exists at path
    path = f"notebook/results/{runner_cls_name}_{univ3_pool_addr}_{runner.maintenance}_{runner.utilization}_{runner.skew}_{runner.leverage}_{runner.blocks_held}_{start}_{stop}_{step}.csv"
    if os.path.exists(path):
        os.remove(path)

    if stop < 0:
        stop = None

    args = [path, start, stop, step]
    runner.backtest(*args)
