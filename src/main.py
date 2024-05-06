import json
from queue import Queue
from typing import Any
import arrow
from ibapi.contract import Contract
import time
import os
from threading import Thread
import numpy as np
from pandas import DataFrame
import json

from algorithems.analysis import get_best_ratio
from algorithems.data_transform import get_extremums
from consts.algorithem_consts import SCORE_GROUP_RANGE
from consts.data_consts import GROUPS_FILE_PATH
from consts.time_consts import (
    BAR_SIZE_SECONDS,
    DATETIME_FORMATTING,
    HOURS_FROM_START,
    SECONDS_FROM_END,
    TIMEZONE,
)
from ib.app import IBapi  # type: ignore
from models.evaluation import Evaluation, EvaluationResults
from logger.logger import logger
from models.trading import GroupRatio


def get_stocks_json() -> Any:
    path = os.environ.get("STOCKS_FILE_PATH")
    if not path:
        raise ValueError("STOCKS_FILE_PATH environment variable not set")
    with open(path, "r") as stocks_file:
        return json.load(stocks_file)


def get_evaluations() -> list[Evaluation]:
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


def get_historical_data(
    app: IBapi, id: int, evaluation: Evaluation, response_queue: Queue[Any]
) -> DataFrame:
    contract = Contract()
    contract.symbol = evaluation.symbol
    contract.secType = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"

    endDate = f"{arrow.get(evaluation.datetime, TIMEZONE).shift(hours=HOURS_FROM_START).format(DATETIME_FORMATTING)} {TIMEZONE}"
    app.reqHistoricalData(
        id,
        contract,
        endDate,  # end date time
        f"{SECONDS_FROM_END} S",  # duration
        f"{BAR_SIZE_SECONDS} secs",  # bar size
        "MIDPOINT",  # what to show
        0,  # is regular trading hours
        1,  # format date
        False,  # keep up to date
        [],  # chart options
    )
    df: DataFrame = response_queue.get()

    return df


def split_to_groups(
    evaluations_raw_data: list[EvaluationResults],
) -> list[list[EvaluationResults]]:
    groups: list[list[EvaluationResults]] = []

    for lower_bound_range in np.arange(-10, 10, SCORE_GROUP_RANGE):
        curr_group: list[EvaluationResults] = []
        for evaluation_raw_data in evaluations_raw_data:
            curr_score = evaluation_raw_data.evaluation.score
            if lower_bound_range <= curr_score and (
                lower_bound_range == 10 - SCORE_GROUP_RANGE
                or curr_score < lower_bound_range + SCORE_GROUP_RANGE
            ):
                curr_group.append(evaluation_raw_data)
        groups.append(curr_group)
    return groups


def save_groups_to_file(groups: list[GroupRatio]) -> None:
    groups_json = json.dumps([group.get_json() for group in groups])
    with open(GROUPS_FILE_PATH, "w") as groups_file:
        groups_file.write(groups_json)


def iterate_evaluations(
    app: IBapi, evaluations: list[Evaluation], response_queue: Queue[Any]
) -> None:
    evaluations_raw_data: list[EvaluationResults] = []
    for index, evaluation in enumerate(
        evaluations[0:40]
    ):  # TODO: change this when you're ready
        df: DataFrame = get_historical_data(app, index, evaluation, response_queue)
        if df is None:
            logger.error("Error getting data for evaluation: %s", evaluation)
            continue
        extremums = get_extremums(df)
        evaluations_raw_data.append(
            EvaluationResults(evaluation=evaluation, data=extremums)
        )
    groups: list[list[EvaluationResults]] = split_to_groups(evaluations_raw_data)
    group_ratios: list[GroupRatio] = []
    for index, group in enumerate(groups):
        if len(group) == 0:
            continue
        best_ratio = get_best_ratio(group)
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


def main() -> None:
    evaluations = get_evaluations()
    queue = Queue[Any]()
    app = IBapi(queue)
    app.connect("127.0.0.1", 7497, 1)
    thread = Thread(target=app.run)
    thread.start()

    time.sleep(2)
    iterate_evaluations(app, evaluations, queue)
    thread.join()
    # app.disconnect()


if __name__ == "__main__":
    main()
