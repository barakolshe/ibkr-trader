from queue import Queue
import time
from typing import Any
import arrow
from pandas import DataFrame

from algorithems.analysis import get_best_ratio
from algorithems.data_transform import get_extremums
from consts.algorithem_consts import SCORE_GROUP_RANGE
from consts.time_consts import TIMEZONE
from ib.app import IBapi  # type: ignore
from ib.wrapper import get_historical_data
from controllers.evaluation.groups import split_to_groups
from integrations.cloud.s3 import get_stocks_json_from_bucket
from models.evaluation import Evaluation, EvaluationResults
from logger.logger import logger
from models.trading import GroupRatio
from persistency.data_handler import save_groups_to_file
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
) -> None:
    while True:
        sleep_until_time(kill_queue)
        if not kill_queue.empty():
            return
        logger.info("Iterating evaluations")
        evaluations_raw_data: list[EvaluationResults] = []
        for index, evaluation in enumerate(
            evaluations
        ):  # TODO: change this when you're ready
            df: DataFrame = get_historical_data(app, evaluation, response_queue, index)
            if df is None:
                logger.error("Error getting data for evaluation: %s", evaluation)
                continue
            extremums = get_extremums(df)
            evaluations_raw_data.append(
                EvaluationResults(evaluation=evaluation, data=extremums)
            )
        logger.info("Finished getting data for all evaluations")
        groups: list[list[EvaluationResults]] = split_to_groups(evaluations_raw_data)
        group_ratios: list[GroupRatio] = []
        for index, group in enumerate(groups):
            if len(group) == 0:
                continue
            best_ratio = get_best_ratio(group)
            if best_ratio is None:
                continue
            group_ratios.append(
                GroupRatio(
                    score_range=(
                        D(-10 + (index * SCORE_GROUP_RANGE)),
                        D(-10 + (index + 1) * SCORE_GROUP_RANGE),
                    ),
                    target_profit=best_ratio["target_profit"],
                    stop_loss=best_ratio["stop_loss"],
                    average=best_ratio["average"],
                    urls=[evaluation.evaluation.url for evaluation in group],
                )
            )
        save_groups_to_file(group_ratios)


def get_evaluations() -> list[Evaluation]:
    logger.info("Getting evaluations")
    evaluations: list[Evaluation] = []

    stocks_json = get_stocks_json_from_bucket()
    for stock in stocks_json:
        for evaluation in stock["evaluations"]:
            for evaluated_stock in evaluation["stocks"]:
                evaluations.append(
                    Evaluation(
                        datetime=arrow.get(
                            evaluation["article_date"],
                            "YYYY-MM-DD HH:mm:ss",
                            tzinfo="US/Eastern",
                        ).datetime,
                        score=evaluated_stock["score"],
                        symbol=evaluated_stock["symbol"],
                        url=evaluation["article_url"],
                    )
                )
    return evaluations
