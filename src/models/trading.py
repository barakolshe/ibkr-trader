from typing import Annotated, Any
from pydantic import BaseModel

from models.article import Article


def checkScoreValidation(score: float) -> float:
    assert score >= -10 and score <= 10, "Score must be between 0 and 10"
    return score


class GroupRatio(BaseModel):
    score_range: tuple[float, float]
    target_profit: float
    stop_loss: float
    average: float

    def get_json(self) -> dict[str, Any]:
        return {
            "score_range": self.score_range,
            "target_profit": self.target_profit,
            "stop_loss": self.stop_loss,
            "average": self.average,
        }


class Stock(BaseModel):
    symbol: str
    score: Annotated[float, checkScoreValidation]
    article: Article
