from controllers.evaluation.evaluate import get_evaluations


def test_get_evaluations() -> None:
    evaluations = get_evaluations()
    assert len(evaluations) > 0
