from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Evaluation(BaseModel):
    timestamp: datetime
    ticker: str
    exchange: Optional[str]
    url: str
