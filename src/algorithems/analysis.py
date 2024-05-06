import math
from typing import Any, Optional
from numpy import Infinity
import numpy as np
from pandas import DataFrame

from consts.time_consts import BAR_SIZE_SECONDS, HOURS_FROM_START, SECONDS_FROM_END
from models.evaluation import EvaluationResults
from utils.math_utils import round_decimal
from utils.time_utils import hours_to_seconds


def get_profit_for_ratio(
    target_profit: float, stop_loss: float, evaluation_result: list[float]
) -> float:
    if target_profit > 0 and stop_loss > 0:
        raise ValueError("Both target_profit and stop_loss must be negative")
    if target_profit < 0 and stop_loss < 0:
        raise ValueError("Both target_profit and stop_loss must be positive")

    if target_profit > 0:
        for curr_result in evaluation_result:
            if curr_result >= target_profit:
                return target_profit
            if curr_result <= stop_loss:
                return stop_loss
    else:
        for curr_result in evaluation_result:
            if curr_result <= target_profit:
                return 0 - target_profit
            if curr_result >= stop_loss:
                return 0 - stop_loss

    return evaluation_result[-1]


def get_best_average(averages_list: list[dict[str, Any]]) -> dict[str, float]:
    best_average = {"target_profit": 0, "stop_loss": 0, "average": -Infinity}
    for average in averages_list:
        if average["average"] > best_average["average"]:
            best_average = average
    return best_average


def get_stop_loss(x: float) -> float:
    if x > 0:
        return round_decimal(0 - (0.183673 * x + 0.816326))
    else:
        return round_decimal(0 - (0.183673 * x - 0.816326))


def get_best_ratio(
    evaluation_results: list[EvaluationResults],
) -> Optional[dict[str, float]]:
    if len(evaluation_results) == 0:
        return None
    averages: list[dict[str, float]] = []
    for target_profit in np.arange(-50, 50, 0.5):
        stop_loss = get_stop_loss(target_profit)
        profits: list[float] = []
        for curr_result in evaluation_results:
            profit = get_profit_for_ratio(target_profit, stop_loss, curr_result.data)
            profits.append(profit)

        average = sum(profits) / len(profits)
        averages.append(
            {"target_profit": target_profit, "stop_loss": stop_loss, "average": average}
        )

    best_average = get_best_average(averages)
    return best_average
