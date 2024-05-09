from queue import Queue
from typing import Any
import arrow
from pandas import DataFrame

from algorithems.analysis import get_best_ratio
from algorithems.data_transform import get_extremums
from consts.algorithem_consts import SCORE_GROUP_RANGE
from ib.app import IBapi  # type: ignore
from ib.wrapper import get_historical_data
from controllers.evaluation.groups import split_to_groups
from models.evaluation import Evaluation, EvaluationResults
from logger.logger import logger
from models.trading import GroupRatio
from persistency.data_handler import get_stocks_json, save_groups_to_file


def iterate_evaluations(
    app: IBapi, evaluations: list[Evaluation], response_queue: Queue[Any]
) -> None:
    logger.info("Iterating evaluations")
    evaluations_raw_data: list[EvaluationResults] = []
    for index, evaluation in enumerate(
        evaluations[0:10]
    ):  # TODO: change this when you're ready
        df: DataFrame = get_historical_data(app, evaluation, response_queue)
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
                    -10 + (index * SCORE_GROUP_RANGE),
                    -10 + (index + 1) * SCORE_GROUP_RANGE,
                ),
                target_profit=best_ratio["target_profit"],
                stop_loss=best_ratio["stop_loss"],
                average=best_ratio["average"],
            )
        )
    save_groups_to_file(group_ratios)


def get_evaluations() -> list[Evaluation]:
    logger.info("Getting evaluations")
    evaluations: list[Evaluation] = []

    stocks_json = get_stocks_json()
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
                    )
                )
    return evaluations
