import json
from queue import Queue
import time
from typing import Any
import arrow
from pandas import DataFrame
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import mplfinance as mpf

from algorithems.analysis import get_best_ratio
from algorithems.data_transform import get_extremums
from consts.algorithem_consts import SCORE_GROUP_RANGE
from consts.time_consts import TIMEZONE
from ib.app import IBapi  # type: ignore
from ib.wrapper import get_historical_data
from controllers.evaluation.groups import split_to_groups
from integrations.cloud.s3 import get_stocks_json_from_bucket
from models.app_error import AppError
from models.evaluation import Evaluation, EvaluationResults
from logger.logger import logger
from models.trading import GroupRatio
from persistency.data_handler import save_groups_to_file
from utils.itertools_utils import empty_queue
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
    logger.info("Iterating evaluations")
    evaluations_results: list[EvaluationResults] = []
    for index, evaluation in enumerate(
        evaluations[0:10]
    ):  # TODO: change this when you're ready
        df: DataFrame = get_historical_data(app, evaluation, response_queue, index)
        if isinstance(df, AppError):
            logger.error("Error getting data for evaluation: %s", evaluation)
            time.sleep(2)
            empty_queue(response_queue)
            continue
        extremums = get_extremums(df)
        evaluations_results.append(
            EvaluationResults(evaluation=evaluation, data=extremums, dataframe=df)
        )

    group = evaluations_results
    best_ratio = get_best_ratio(group)
    if best_ratio is None:
        logger.error("No best ratio found")
        return
    ratio = GroupRatio(
        score_range=(D("0"), D("0")),
        target_profit=best_ratio["target_profit"],
        stop_loss=best_ratio["stop_loss"],
        average=best_ratio["average"],
        urls=[str(len(evaluations_results))],
    )

    with PdfPages("multipage_pdf.pdf") as pdf:  # type: ignore
        for evaluation_result in evaluations_results:
            df = evaluation_result.dataframe
            df["volume"] = df["volume"].astype(float)
            fig, _ = mpf.plot(df, type="candle", returnfig=True)
            if fig is None:
                continue
            txt = f"symbol: {evaluation_result.evaluation.symbol}, exchange: {evaluation_result.evaluation.exchange}, date: {evaluation_result.evaluation.datetime}"
            plt.text(0.05, 0.95, txt, transform=fig.transFigure, size=18)
            pdf.savefig(fig)
            plt.close()


def get_evaluations() -> list[Evaluation]:
    logger.info("Getting evaluations")
    evaluations: list[Evaluation] = []
    data: Any = None
    with open("data/actions.json") as actions:
        data = json.load(actions)

    for article in data:
        for evaluated_stock in article["stocks"]:
            evaluations.append(
                Evaluation(
                    datetime=arrow.get(
                        article["article_date"],
                        "YYYY-MM-DD HH:mm:ss",
                        tzinfo="US/Eastern",
                    ).datetime,
                    symbol=evaluated_stock["symbol"],
                    exchange=evaluated_stock["exchange"],
                )
            )
    return evaluations
