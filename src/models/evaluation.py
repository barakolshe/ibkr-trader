from datetime import datetime
from decimal import Decimal
from pandas import DataFrame
from pydantic import BaseModel, ConfigDict

from models.math import Extremum


class Evaluation(BaseModel):
    datetime: datetime
    # score: Decimal
    symbol: str
    exchange: str
    url: str


class EvaluationResults(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluation: Evaluation
    data: list[Extremum]
    dataframe: DataFrame
