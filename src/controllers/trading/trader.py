from datetime import datetime, timedelta
import arrow

from consts.time_consts import TIMEZONE
from controllers.trading.strategy import TestStrategy
from models.evaluation import Evaluation
from logger.logger import logger, log_important


def compare_dates(actual_date: arrow.Arrow, article_datetime: arrow.Arrow) -> bool:
    if actual_date.weekday() == 0:
        return (
            actual_date.shift(days=-3).replace(hour=16, minute=0, second=0)
            < article_datetime
            < actual_date.replace(hour=9, minute=30, second=0)
        )
    else:
        return (
            actual_date.shift(days=-1).replace(hour=16, minute=0, second=0)
            < article_datetime
            < actual_date.replace(hour=9, minute=30, second=0)
        )


class BaseTrader:
    def test_strategy(
        self,
        evaluations: list[Evaluation],
    ) -> None:
        cash: float = 40000
        # min_date = min(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])
        min_date = arrow.get(evaluations[0].timestamp, tzinfo=TIMEZONE).replace(
            month=6, day=1, hour=0, minute=0
        )
        max_date = max(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])

        logger.info(f"{min_date}  -   {max_date}")

        date_range = [
            min_date.datetime + timedelta(days=delta)
            for delta in range((max_date.datetime - min_date.datetime).days + 1)
        ]

        log_important(f"cash: {cash}", "info")
        for date in date_range:
            if date.weekday() == 5 or date.weekday() == 6:
                continue
            filtered_evaluations = [
                evaluation
                for evaluation in evaluations
                if compare_dates(arrow.get(date), arrow.get(evaluation.timestamp))
            ]

            if len(filtered_evaluations) == 0:
                continue
            logger.info(f"Trading for {date.date()}")
            trader = TestStrategy(date, is_testing=True, initial_cash=cash)
            trader.main_loop(filtered_evaluations)
            filtered_evaluations = []
            cash = trader.cash

            log_important(f"cash: {trader.cash}", "info")
