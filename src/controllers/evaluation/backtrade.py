import json
from typing import Any
import arrow

from models.evaluation import Evaluation
from logger.logger import logger

actions_file_name = "data/actions.json"


def get_evaluations(delay: int) -> list[Evaluation]:
    logger.info("Getting evaluations")
    evaluations: list[Evaluation] = []
    data: Any = None

    with open(actions_file_name) as actions:
        data = json.load(actions)

    bad_urls = []
    for evaluated_stock in data:
        try:
            evaluations.append(
                Evaluation(
                    timestamp=arrow.get(
                        evaluated_stock["date"],
                        "YYYY-MM-DD HH:mm:ss",
                        tzinfo="US/Eastern",
                    )
                    .shift(minutes=delay)
                    .datetime,
                    symbol=evaluated_stock["ticker"],
                    exchange=evaluated_stock["exchange"],
                    url=evaluated_stock["url"],
                )
            )
        except:
            bad_urls.append(evaluated_stock["url"])
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
