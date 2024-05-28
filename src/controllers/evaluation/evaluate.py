from decimal import Decimal
import json
from queue import Queue
import time
from typing import Any
import arrow
from pandas import DataFrame
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import mplfinance as mpf
import matplotlib.ticker as ticker

from algorithems.analysis import get_best_ratio, get_profit_for_ratio
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


curr_precision = Decimal("Infinity")


def fake_format_price(x: float, _: None = None) -> str:
    def check_curr_precision(precision: Decimal) -> None:
        global curr_precision
        if curr_precision > precision:
            curr_precision = precision

    x_decimal = D(x)
    if x_decimal % D("0.01") != D("0"):
        check_curr_precision(Decimal("0.001"))
        return str(x_decimal.quantize(Decimal("0.001")))
    elif x_decimal % D("0.1") != D("0"):
        check_curr_precision(Decimal("0.01"))
        return str(x_decimal.quantize(Decimal("0.01")))
    elif x_decimal % D("1") != D("0"):
        check_curr_precision(Decimal("0.1"))
        return str(x_decimal.quantize(Decimal("0.1")))
    else:
        check_curr_precision(Decimal("1"))
        return str(x_decimal.quantize(Decimal("1")))


def format_price(x: float, _: None = None) -> str:
    global curr_precision
    x_decimal = D(x)
    return str(x_decimal.quantize(curr_precision))


def iterate_evaluations(
    app: IBapi,
    evaluations: list[Evaluation],
    response_queue: Queue[Any],
    kill_queue: Queue[Any],
) -> None:
    global curr_precision
    logger.info("Iterating evaluations")
    evaluations_results: list[EvaluationResults] = []
    for index, evaluation in enumerate(
        evaluations[0:5]
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

    group = evaluations_results[0:1]
    best_ratio = get_best_ratio(group)
    if best_ratio is None:
        logger.error("No best ratio found")
        return
    ratio = GroupRatio(
        score_range=(D("0"), D("0")),
        target_profit=best_ratio["target_profit"],
        stop_loss=best_ratio["stop_loss"],
        average=best_ratio["average"],
        urls=[],
    )

    with PdfPages("fake_pdf.pdf") as fake_pdf:  # type: ignore
        with PdfPages("multipage_pdf.pdf") as pdf:  # type: ignore
            plt.figure()
            plt.axis("off")
            best_ratio_text = f"Target profit: {ratio.target_profit}, Stop loss: {ratio.stop_loss}, Average: {ratio.average}"
            plt.text(0.5, 0.5, best_ratio_text, ha="center", va="center")
            pdf.savefig()
            plt.close()
            for evaluation_result in evaluations_results[0:1]:
                df = evaluation_result.dataframe
                df["volume"] = df["volume"].astype(float)

                # fake
                fig, axis = mpf.plot(
                    df,
                    type="candle",
                    returnfig=True,
                    datetime_format="%H:%M",
                )
                axis[0].yaxis.set_major_formatter(
                    ticker.FuncFormatter(fake_format_price)
                )
                fake_pdf.savefig(fig)
                plt.close()
                # real
                market_colors = mpf.make_marketcolors(up="g", down="r")
                style = mpf.make_mpf_style(marketcolors=market_colors)
                fig, axis = mpf.plot(
                    df,
                    type="candle",
                    returnfig=True,
                    style=style,
                    datetime_format="%H:%M",
                )
                axis[0].yaxis.set_major_formatter(ticker.FuncFormatter(format_price))
                if fig is None:
                    continue
                profit = get_profit_for_ratio(
                    ratio.target_profit, ratio.stop_loss, evaluation_result.data
                )
                text = f"symbol: {evaluation_result.evaluation.symbol}, exchange: {evaluation_result.evaluation.exchange}, date: {arrow.get(evaluation_result.evaluation.datetime).format('DD-MM-YYYY HH:mm:ss')}"
                profit_text = f"entry price: {evaluation_result.dataframe.iloc[-1]['close']}, profit: {profit}"
                fig.text(0.2, 0.05, text)
                fig.text(0.3, 0.02, profit_text)
                pdf.savefig(fig)
                plt.close()
                curr_precision = Decimal("Infinity")


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
