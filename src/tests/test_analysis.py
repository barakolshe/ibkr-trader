from typing import Any
from algorithems.analysis import get_possible_stop_losses
import numpy as np
from numpy import ndarray as NDArray
from consts.algorithem_consts import ANALYSIS_GAP
from utils.math_utils import D


def test_get_possible_stop_losses() -> None:
    target_profit = D("0.05")
    expected_result: NDArray[Any, Any] = np.arange(
        D("-0.05"), -ANALYSIS_GAP, ANALYSIS_GAP
    )

    result = get_possible_stop_losses(target_profit)

    assert list(result) == list(expected_result)

    target_profit = D("-0.15")
    expected_result = np.arange(ANALYSIS_GAP, D("0.1"), ANALYSIS_GAP)

    result = get_possible_stop_losses(target_profit)

    assert list(result) == list(expected_result)
