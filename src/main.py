import os
from typing import Optional
from controllers.evaluation.backtrade import (
    get_evaluations,
)
from controllers.trading.new_strategy import NewTrader
from controllers.trading.trader import BaseTrader


def trade_with_backtrader() -> None:
    evaluations = get_evaluations()
    base_trader = BaseTrader()

    base_trader.test_strategy(evaluations)


if __name__ == "__main__":
    trade_with_backtrader()
