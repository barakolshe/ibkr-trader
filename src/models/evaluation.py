from datetime import datetime
from pydantic import BaseModel, ConfigDict


class Evaluation(BaseModel):
    datetime: datetime
    score: float
    symbol: str


class EvaluationResults(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluation: Evaluation
    data: list[float]
