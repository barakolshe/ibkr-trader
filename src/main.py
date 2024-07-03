import os
from typing import Optional
from controllers.evaluation.backtrade import (
    get_evaluations,
)
from controllers.trading.trader import BaseTrader, TestTrader, PaperTrader, LiveTrader


def trade_with_backtrader() -> None:
    evaluations = get_evaluations()

    target_evaluations = [evaluation for evaluation in evaluations]

    trader: Optional[BaseTrader] = None
    mode = os.environ.get("MODE")
    if mode == "TEST":
        trader = TestTrader()
    elif mode == "PAPER":
        trader = PaperTrader()
    elif mode == "LIVE":
        trader = LiveTrader()
    else:
        raise Exception("No mode was chosen")

    if not trader:
        raise Exception("No trader was chosen")
    trader.test_strategy(target_evaluations)


if __name__ == "__main__":
    trade_with_backtrader()
