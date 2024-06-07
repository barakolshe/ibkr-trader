from decimal import Decimal
import json
from queue import Queue
import time
from typing import Any, Optional
import arrow
import hashlib

from algorithems.analysis import (
    get_average_for_ratio,
    get_best_ratio,
)
from algorithems.data_transform import get_extremums
from consts.time_consts import TIMEZONE
from ib.app import IBapi  # type: ignore
from ib.wrapper import get_historical_data
from models.evaluation import Evaluation, EvaluationResults
from logger.logger import logger
from models.trading import GroupRatio
from utils.math_utils import D


def sleep_until_time(kill_queue: Queue[Any]) -> None:
    while True:
        curr_date = arrow.now(tz=TIMEZONE)
        if curr_date.hour == 17:
            return
        else:
            time.sleep(20)
        if not kill_queue.empty():
            return


def iterate_evaluations(
    app: IBapi,
    evaluations: list[Evaluation],
    response_queue: Queue[Any],
    kill_queue: Queue[Any],
    time_limit: int,
    target_profit: Optional[Decimal] = None,
    stop_loss: Optional[Decimal] = None,
) -> Optional[tuple[list[EvaluationResults], GroupRatio]]:
    logger.info("Iterating evaluations")
    evaluations_results: list[EvaluationResults] = []
    for index, evaluation in enumerate(evaluations):
        df = get_historical_data(app, evaluation, time_limit, response_queue, index)
        if df is None or df.empty:
            continue
        original_price = df.iloc[0]["close"]
        if original_price < D("0.5"):
            logger.error("Price is too low")
            continue
        extremums = get_extremums(df)
        if len(extremums) == 0:
            continue
        logger.info("Got extremums for evaluation: %s", evaluation)
        curr_results = EvaluationResults(
            evaluation=evaluation, data=extremums, df=df, duration=time_limit
        )
        evaluations_results.append(curr_results)

    group = evaluations_results
    if len(group) == 0:
        return None
    if target_profit is None or stop_loss is None:
        best_ratio = get_best_ratio(group)
        if best_ratio is None:
            logger.error("No best ratio found")
            return None
        ratio = GroupRatio(
            score_range=(D("0"), D("0")),
            target_profit=best_ratio["target_profit"],
            stop_loss=best_ratio["stop_loss"],
            average=best_ratio["average"],
            urls=[],
        )
    else:
        profit = get_average_for_ratio(
            group,
            target_profit,
            stop_loss,
        )
        ratio = GroupRatio(
            score_range=(D("0"), D("0")),
            target_profit=profit["target_profit"],
            stop_loss=profit["stop_loss"],
            average=profit["average"],
            urls=[],
        )

    return evaluations_results, ratio


actions_file_name = "data/actions.json"


def get_evaluations(delay: int) -> list[Evaluation]:
    logger.info("Getting evaluations")
    evaluations: list[Evaluation] = []
    data: Any = None
    with open(actions_file_name) as actions:
        data = json.load(actions)

    bad_urls = []
    for article in data:
        for evaluated_stock in article["stocks"]:
            try:
                evaluations.append(
                    Evaluation(
                        timestamp=arrow.get(
                            article["article_date"],
                            "YYYY-MM-DD HH:mm:ss",
                            tzinfo="US/Eastern",
                        )
                        .shift(minutes=delay)
                        .datetime,
                        symbol=evaluated_stock["symbol"],
                        state=evaluated_stock["state"],
                        url=article["article_url"],
                    )
                )
            except:
                bad_urls.append(article["article_url"])
                continue

    if len(bad_urls) > 0:
        raise Exception(f"Bad urls: {bad_urls}")
    return evaluations


def get_json_hash() -> str:
    with open(actions_file_name) as actions:
        return str(
            int(hashlib.sha1((actions.read()).encode("utf-8")).hexdigest(), 16)
            % (10**8)
        )
