from datetime import datetime
from algorithems.analysis import get_best_ratio
from models.evaluation import EvaluationResults, Evaluation
from utils.math_utils import D


# def test_get_best_ratio() -> None:
#     ratio = get_best_ratio(
#         [
#             EvaluationResults(
#                 data=[
#                     D("0.007017543859649145"),
#                     D("-0.007017543859649145"),
#                     D("0.007017543859649145"),
#                     D("-0.03508771929824561"),
#                     D("-0.03508771929824561"),
#                 ],
#                 evaluation=Evaluation(
#                     datetime=datetime(2021, 1, 1),
#                     score=D("0.5"),
#                     symbol="AAPL",
#                     url="www.google.com",
#                 ),
#             )
#         ]
#     )
#     if ratio is None:
#         assert False
#     assert ratio["target_profit"] == D("-0.0350")
#     assert ratio["average"] == D("0.0350")
