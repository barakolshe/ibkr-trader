from datetime import datetime
from algorithems.analysis import get_best_ratio, get_stop_loss
from models.evaluation import EvaluationResults, Evaluation


def test_get_best_ratio() -> None:
    ratio = get_best_ratio(
        [
            EvaluationResults(
                data=[
                    0.7017543859649145,
                    -0.7017543859649145,
                    0.7017543859649145,
                    -3.508771929824561,
                    -3.508771929824561,
                ],
                evaluation=Evaluation(
                    datetime=datetime(2021, 1, 1), score=0.5, symbol="AAPL"
                ),
            )
        ]
    )
    if ratio is None:
        assert False
    assert ratio["target_profit"] == -3.5
    assert ratio["average"] == 3.5


def test_get_stop_loss() -> None:
    MINIMUM_SHIFT = 0.01
    assert -10 - MINIMUM_SHIFT < get_stop_loss(50) < -10 + MINIMUM_SHIFT
    assert -1 - MINIMUM_SHIFT < get_stop_loss(1) < -1 + MINIMUM_SHIFT
    assert 10 - MINIMUM_SHIFT < get_stop_loss(-50) < 10 + MINIMUM_SHIFT
    assert 1 - MINIMUM_SHIFT < get_stop_loss(-1) < 1 + MINIMUM_SHIFT
