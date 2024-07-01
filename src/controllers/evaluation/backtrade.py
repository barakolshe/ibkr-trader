from datetime import datetime
import json
from typing import Any, Optional
import arrow

from models.evaluation import Evaluation
from logger.logger import logger

actions_file_name = "data/actions.json"


def get_datetime(date_string: str) -> Optional[datetime]:
    arrow_article_date = arrow.get(
        date_string, "YYYY-MM-DD HH:mm:ss", tzinfo="US/Eastern"
    )
    article_date: Optional[datetime] = None
    if arrow_article_date.hour < 9 or (
        arrow_article_date.hour == 9 and arrow_article_date.minute < 30
    ):
        article_date = arrow_article_date.replace(hour=0, minute=0, second=0).datetime
    elif arrow_article_date.hour >= 16:
        article_date = (
            arrow_article_date.shift(days=1)
            .replace(hour=0, minute=0, second=0)
            .datetime
        )

    return article_date


def get_evaluations() -> list[Evaluation]:
    logger.info("Getting evaluations")
    evaluations: list[Evaluation] = []
    data: Any = None

    with open(actions_file_name) as actions:
        data = json.load(actions)

    bad_urls = []
    for evaluated_stock in data:
        try:
            article_date = get_datetime(evaluated_stock["date"])
            if article_date is None:
                continue
            curr_evaluation = Evaluation(
                timestamp=article_date,
                symbol=evaluated_stock["ticker"],
                exchange=evaluated_stock["exchange"],
                url=evaluated_stock["url"],
            )
            if [
                evaluation
                for evaluation in evaluations
                if evaluation.symbol == curr_evaluation.symbol
                and evaluation.timestamp.date() == curr_evaluation.timestamp.date()
            ]:
                continue
            evaluations.append(curr_evaluation)
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
