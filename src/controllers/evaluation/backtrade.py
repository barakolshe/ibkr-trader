from decimal import Decimal
import hashlib
import json
import threading
from typing import Any
import arrow

from controllers.trading.fetchers.wrapper import (
    get_historical_data,
    complete_missing_values,
)
from controllers.trading.trader import Trader
from models.evaluation import Evaluation, TestEvaluationResults
from logger.logger import logger

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
        print(f"Bad urls: {bad_urls}")
    return filter_evaluations(evaluations)


def filter_evaluations(evaluations: list[Evaluation]) -> list[Evaluation]:
    filtered_evaluations: list[Evaluation] = []

    for curr_evaluation in evaluations:
        existing_evaluations = [
            evaluation
            for evaluation in filtered_evaluations
            if evaluation.symbol == curr_evaluation.symbol
            and evaluation.timestamp == curr_evaluation.timestamp
        ]
        if len(existing_evaluations) == 0:
            filtered_evaluations.append(curr_evaluation)

    return filtered_evaluations


def get_json_hash() -> str:
    with open(actions_file_name) as actions:
        return str(
            int(hashlib.sha1((actions.read()).encode("utf-8")).hexdigest(), 16)
            % (10**8)
        )


def backtrade(
    evaluations: list[Evaluation],
    time_limit: int,
    target_profit: Decimal,
    stop_loss: Decimal,
) -> None:
    evaluation_results: list[TestEvaluationResults] = []

    for index, evaluation in enumerate(evaluations):
        df = get_historical_data(evaluation, time_limit + 60)
        if (
            df is None
            or df.empty
            or arrow.get(df.index[0]).shift(minutes=time_limit)
            > arrow.get(df.index[-1])
        ):
            continue
        df = complete_missing_values(df)
        evaluation_results.append(TestEvaluationResults(evaluation=evaluation, df=df))

    kill_event: threading.Event = threading.Event()
    trader = Trader(kill_event)
    trader.test_strategy(evaluation_results, target_profit, stop_loss, time_limit)
