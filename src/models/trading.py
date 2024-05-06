from typing import Any
from pydantic import BaseModel


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
