from datetime import datetime
from pydantic import BaseModel


class Article(BaseModel):
    website: str
    content: str
    datetime: datetime
