from algorithems.analysis import get_possible_stop_losses
import numpy as np

from consts.algorithem_consts import ANALYSIS_GAP


def test_get_possible_stop_losses() -> None:
    target_profit = 5
    expected_result = np.arange(-5, -ANALYSIS_GAP, ANALYSIS_GAP)

    result = get_possible_stop_losses(target_profit)

    assert list(result) == list(expected_result)

    target_profit = -15
    expected_result = np.arange(ANALYSIS_GAP, 10, ANALYSIS_GAP)

    result = get_possible_stop_losses(target_profit)

    assert list(result) == list(expected_result)
