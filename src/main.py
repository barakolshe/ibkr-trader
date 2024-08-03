import time
from consts.time_consts import TIMEZONE
from consts.trading_consts import get_start_datetime
from controllers.trading.fetcher import (
    get_actions,
)
from controllers.trading.strategy import PaperStrategy
from controllers.trading.trader import BaseTrader, compare_dates, filter_evaluations
import arrow
import boto3
from logger.logger import logger
from dotenv import load_dotenv

load_dotenv()

US_EXCHANGES = ["NYSE", "NASDAQ", "AMEX", "NYSEA"]
AMAZON_BUCKET_NAME: str = "barak-trading-bucket"


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


def sleep_until(target_datetime: arrow.Arrow) -> bool:
    while arrow.now(tz="US/Eastern") < target_datetime:
        time.sleep(30)
        if check_kill_all_command():
            return False
    return True


def test_strategy() -> None:
    evaluations = get_actions(exchanges=US_EXCHANGES, all=True)
    base_trader = BaseTrader()

    base_trader.test_strategy(evaluations)


def live_trade(next_valid_order_id: int) -> int:
    evaluations = get_actions(exchanges=US_EXCHANGES, all=False)
    filtered_evaluations = [
        evaluation
        for evaluation in evaluations
        if compare_dates(arrow.now(tz=TIMEZONE), arrow.get(evaluation.timestamp))
    ]
    logger.info("Initializing paper strategy")
    filtered_evaluations = filter_evaluations(filtered_evaluations)
    strategy = PaperStrategy(
        arrow.now(tz=TIMEZONE)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .datetime,
        next_valid_order_id,
    )
    logger.info("Starting main loop")
    next_valid_order_id = strategy.main_loop(filtered_evaluations)
    return next_valid_order_id


def live_trade_loop() -> None:
    logger.info("Running")
    next_valid_order_id = 1
    while True:
        now_date = arrow.now(tz=TIMEZONE)
        days_shift = 7 - now_date.weekday() if now_date.weekday() > 5 else 1
        logger.info(f"Now date {now_date}, ")
        if now_date < get_start_datetime(now_date).shift(minutes=-4):
            logger.info(
                f"Sleeping {(get_start_datetime(now_date).shift(minutes=-4).datetime - now_date.datetime).seconds // 60} minutes"
            )
            if not sleep_until(get_start_datetime(now_date).shift(minutes=-4)):
                return
            next_valid_order_id = live_trade(next_valid_order_id)
        if not sleep_until(
            get_start_datetime(now_date).shift(minutes=-10, days=days_shift)
        ):
            return


if __name__ == "__main__":
    live_trade_loop()
