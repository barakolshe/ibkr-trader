from datetime import datetime
import time
from consts.time_consts import TIMEZONE
from consts.trading_consts import get_start_datetime
from controllers.trading.fetcher import (
    get_actions,
)
from controllers.trading.strategy import PaperStrategy
from controllers.trading.trader import BaseTrader, compare_dates
import arrow
import boto3

US_EXCHANGES = ["NYSE", "NASDAQ", "AMEX", "NYSEA"]
AMAZON_BUCKET_NAME: str = "barak-trading-bucket"


def sleep_until(target_datetime: datetime) -> None:
    diff = target_datetime - arrow.now(tz="US/Eastern").datetime
    time.sleep(diff.total_seconds())


def check_kill_all_command() -> bool:
    s3_client = boto3.client("s3")
    try:
        s3_client.get_object(Bucket=AMAZON_BUCKET_NAME, Key="exit2.json")
        s3_client.delete_objects(
            Bucket=AMAZON_BUCKET_NAME,
            Delete={
                "Objects": [
                    {
                        "Key": "exit2.json",
                    },
                ],
            },
        )
        return True
    except:
        return False


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
    while True:
        days_shift = (
            7 - arrow.now(tz="US/Eastern").weekday()
            if arrow.now(tz="US/Eastern").weekday() > 5
            else 1
        )
        sleep_until(
            arrow.now(tz="US/Eastern")
            .shift(day=days_shift)
            .replace(hour=10, minute=45, second=0)
            .datetime
        )
        if check_kill_all_command():
            break
        live_trade()
