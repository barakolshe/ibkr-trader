import os
from typing import Optional
from controllers.evaluation.backtrade import (
    get_evaluations,
)
from controllers.trading.trader import BaseTrader, LiveTrader, TestTrader


def trade_with_backtrader() -> None:
    evaluations = get_evaluations()

    target_evaluations = [evaluation for evaluation in evaluations]

    trader: Optional[BaseTrader] = None
    if os.environ.get("LIVE") == "True":
        trader = LiveTrader()
    else:
        trader = TestTrader()

    if not trader:
        raise Exception("No trader was chosen")
    trader.test_strategy(target_evaluations)


if __name__ == "__main__":
    trade_with_backtrader()
