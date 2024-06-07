from controllers.evaluation.backtrade import get_evaluations


def test_get_evaluations() -> None:
    evaluations = get_evaluations(10)
    assert len(evaluations) > 0
