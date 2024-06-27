from decimal import Decimal
from typing import Any, Optional
from numpy import Infinity
import numpy as np
from numpy import ndarray as NDArray

from consts.algorithem_consts import ANALYSIS_GAP
from consts.trading_consts import STOP_LOSS
from models.evaluation import EvaluationResults
from models.math import Extremum
from utils.math_utils import D

possible_profits = [
    value
    for value in np.arange(D("-0.5"), D("0.5") + ANALYSIS_GAP, ANALYSIS_GAP)
    if value not in np.arange(D("-0.002") + ANALYSIS_GAP, D("0.002"), ANALYSIS_GAP)
]


def get_profit_for_ratio(
    target_profit: Decimal,
    stop_loss: Decimal,
    evaluation_result: list[Extremum],
) -> Extremum:
    if target_profit > 0 and stop_loss > 0:
        raise ValueError("Both target_profit and stop_loss must be negative")
    if target_profit < 0 and stop_loss < 0:
        raise ValueError("Both target_profit and stop_loss must be positive")

    last = evaluation_result[-1]
    if target_profit > 0:
        for curr_result in evaluation_result:
            if curr_result.value >= target_profit:
                return Extremum(value=target_profit, datetime=curr_result.datetime)
            if curr_result.value <= stop_loss:
                return Extremum(value=stop_loss, datetime=curr_result.datetime)
        return Extremum(value=last.value, datetime=last.datetime)
    else:
        for curr_result in evaluation_result:
            if curr_result.value <= target_profit:
                return Extremum(value=0 - target_profit, datetime=curr_result.datetime)
            if curr_result.value >= stop_loss:
                return Extremum(value=0 - stop_loss, datetime=curr_result.datetime)

        return Extremum(value=0 - last.value, datetime=last.datetime)


def get_best_average(averages_list: list[dict[str, Decimal]]) -> dict[str, Decimal]:
    best_average = {
        "target_profit": D("0"),
        "stop_loss": D("0"),
        "average": D("-Infinity"),
    }
    for average in averages_list:
        if average["average"] > best_average["average"]:
            best_average = average
    return best_average


def get_possible_stop_losses(target_profit: Decimal) -> NDArray[Any, Any]:
    if target_profit > 0:
        return np.arange(
            (0 - STOP_LOSS).max(0 - target_profit), 0 - ANALYSIS_GAP, ANALYSIS_GAP
        )
    else:
        return np.arange(ANALYSIS_GAP, STOP_LOSS.min(0 - target_profit), ANALYSIS_GAP)


def get_average_for_ratio(
    evaluation_results: list[EvaluationResults],
    target_profit: Decimal,
    stop_loss: Decimal,
) -> dict[str, Any]:
    profits: list[Extremum] = []
    for curr_result in evaluation_results:
        profit = get_profit_for_ratio(target_profit, stop_loss, curr_result.data)
        profits.append(profit)

    average = D(sum([profit.value for profit in profits]) / len(profits))
    return {
        "target_profit": target_profit,
        "stop_loss": stop_loss,
        "average": average,
    }


def get_best_ratio(
    evaluation_results: list[EvaluationResults],
) -> Optional[dict[str, Decimal]]:
    if len(evaluation_results) == 0:
        return None
    averages: list[dict[str, Decimal]] = []
    for target_profit in possible_profits:
        for stop_loss in get_possible_stop_losses(target_profit):
            profits: list[Extremum] = []
            for curr_result in evaluation_results:
                profit = get_profit_for_ratio(
                    target_profit, stop_loss, curr_result.data
                )
                profits.append(profit)

            average = D(sum([profit.value for profit in profits]) / len(profits))
            averages.append(
                {
                    "target_profit": target_profit,
                    "stop_loss": stop_loss,
                    "average": average,
                }
            )

    averages = sorted(averages, key=lambda average: average["average"], reverse=True)
    best_average = get_best_average(averages)
    return best_average
