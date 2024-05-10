from decimal import Decimal
import numpy as np

from consts.algorithem_consts import SCORE_GROUP_RANGE
from models.evaluation import EvaluationResults
from models.trading import GroupRatio


def split_to_groups(
    evaluations_raw_data: list[EvaluationResults],
) -> list[list[EvaluationResults]]:
    groups: list[list[EvaluationResults]] = []

    for lower_bound_range in np.arange(-10, 10, SCORE_GROUP_RANGE):
        curr_group: list[EvaluationResults] = []
        for evaluation_raw_data in evaluations_raw_data:
            curr_score = evaluation_raw_data.evaluation.score
            if lower_bound_range <= curr_score and (
                lower_bound_range == 10 - SCORE_GROUP_RANGE
                or curr_score < lower_bound_range + SCORE_GROUP_RANGE
            ):
                curr_group.append(evaluation_raw_data)
        groups.append(curr_group)
    return groups


def get_group_for_score(groups: list[GroupRatio], score: Decimal) -> GroupRatio:
    for group in groups:
        if group.score_range[0] <= score <= group.score_range[1]:
            return group
    raise ValueError("No group found for score")
