from decimal import Decimal
from typing import Annotated, Any
from pydantic import BaseModel
from datetime import datetime

from models.article import Article


def checkScoreValidation(score: Decimal) -> Decimal:
    assert score >= -10 and score <= 10, "Score must be between 0 and 10"
    return score


class GroupRatio(BaseModel):
    score_range: tuple[Decimal, Decimal]
    target_profit: Decimal
    stop_loss: Decimal
    average: Decimal
    urls: list[str]

    def get_json(self) -> dict[str, Any]:
        return {
            "score_range": self.score_range,
            "target_profit": self.target_profit,
            "stop_loss": self.stop_loss,
            "average": self.average,
            "urls": self.urls,
        }


class Stock(BaseModel):
    symbol: str
    score: Annotated[Decimal, checkScoreValidation]
    article: Article

    def get_json(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "article": self.article.get_json(),
        }


class Position(BaseModel):
    symbol: str
    quantity: Decimal
    datetime: datetime
