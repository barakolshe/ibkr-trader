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
        evaluations
    ):  # TODO: change this when you're ready
        df = get_historical_data(app, evaluation, response_queue, index)
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
        curr_results = EvaluationResults(evaluation=evaluation, data=extremums, df=df)
        evaluations_results.append(curr_results)

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
        urls=[],
    )

    evaluations_results = sorted(
        evaluations_results,
        key=lambda result: get_profit_for_ratio(
            ratio.target_profit, ratio.stop_loss, result.data
        ).value,
        reverse=True,
    )

    start_date = min([result.evaluation.timestamp for result in evaluations_results])
    end_date = max([result.evaluation.timestamp for result in evaluations_results])

    average_trade_per_day = len(evaluations_results) / (
        (end_date - start_date).days + 1
    )

    with PdfPages("fake_pdf.pdf") as fake_pdf:  # type: ignore
        with PdfPages("tmp2.pdf") as pdf:  # type: ignore
            plt.figure()
            plt.axis("off")
            best_ratio_text = f"Target profit: {ratio.target_profit}, Stop loss: {ratio.stop_loss}, Average: {ratio.average}"
            dates_text = f"Start date: {start_date}, End date: {end_date}"
            average_per_day_text = f"Average trades per day: {average_trade_per_day}"
            plt.text(0.5, 0.6, best_ratio_text, ha="center", va="center")
            plt.text(0.5, 0.5, dates_text, ha="center", va="center")
            plt.text(0.5, 0.4, average_per_day_text, ha="center", va="center")
            pdf.savefig()
            plt.close()
            for evaluation_result in evaluations_results:
                df = evaluation_result.df
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
                vwap = mpf.make_addplot(df["vwap"], type="line", width=1.5)
                fig, axis = mpf.plot(
                    df,
                    type="candle",
                    returnfig=True,
                    addplot=vwap,
                    volume=True,
                    style=style,
                    datetime_format="%H:%M",
                )
                axis[0].yaxis.set_major_formatter(ticker.FuncFormatter(format_price))
                if fig is None:
                    continue
                profit = get_profit_for_ratio(
                    ratio.target_profit, ratio.stop_loss, evaluation_result.data
                )
                entry_price = evaluation_result.df.iloc[0]["close"]
                entry_datetime = evaluation_result.df.iloc[
                    0
                ].name.to_pydatetime()  # type: ignore
                text = f"symbol: {evaluation_result.evaluation.symbol}, exchange: {evaluation_result.evaluation.exchange}, date: {arrow.get(evaluation_result.evaluation.timestamp).format('DD-MM-YYYY HH:mm:ss')}"
                profit_text = f"entry price: {entry_price}, profit: {profit.value:.4f}, time: {profit.datetime - entry_datetime}"
                url = f"{evaluation_result.evaluation.url}"
                fig.text(0.01, 0.05, text)
                fig.text(0.55, 0.05, profit_text)
                fig.text(0.01, 0.02, url, fontsize=5)
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
                    timestamp=arrow.get(
                        article["article_date"],
                        "YYYY-MM-DD HH:mm:ss",
                        tzinfo="US/Eastern",
                    ).datetime,
                    symbol=evaluated_stock["symbol"],
                    exchange=evaluated_stock["exchange"],
                    url=article["article_url"],
                )
            )
    return evaluations
