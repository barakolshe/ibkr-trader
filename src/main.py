from datetime import datetime
from consts.time_consts import TIMEZONE
from controllers.trading.fetcher import (
    get_actions,
)
from controllers.trading.strategy import PaperStrategy
from controllers.trading.trader import BaseTrader, compare_dates
import arrow

US_EXCHANGES = ["NYSE", "NASDAQ", "AMEX", "NYSEA"]


def test_strategy() -> None:
    evaluations = get_actions(exchanges=US_EXCHANGES, all=True)
    base_trader = BaseTrader()

    base_trader.test_strategy(evaluations)


def live_trade() -> None:
    evaluations = get_actions(exchanges=US_EXCHANGES, all=False)
    filtered_evaluations = [
        evaluation
        for evaluation in evaluations
        if compare_dates(arrow.now(tz=TIMEZONE), arrow.get(evaluation.timestamp))
    ]
    strategy = PaperStrategy(
        arrow.now(tz=TIMEZONE)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .datetime
    )
    strategy.main_loop(filtered_evaluations)


if __name__ == "__main__":
    test_strategy()
