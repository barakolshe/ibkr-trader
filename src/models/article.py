from datetime import datetime, tzinfo
from typing import Any
import arrow
from pydantic import BaseModel

from consts.time_consts import DATETIME_FORMATTING, TIMEZONE


class Article(BaseModel):
    website: str
    url: str
    content: str
    datetime: datetime

    def get_json(self) -> dict[str, Any]:
        return {
            "website": self.website,
            "url": self.url,
            "content": self.content,
            "datetime": arrow.get(self.datetime).format(DATETIME_FORMATTING),
        }
