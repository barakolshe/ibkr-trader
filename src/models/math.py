from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime


class Extremum(BaseModel):
    value: Decimal
    datetime: datetime
