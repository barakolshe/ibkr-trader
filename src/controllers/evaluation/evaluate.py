from decimal import Decimal
import json
from typing import Any, Optional
import arrow
import hashlib

from algorithems.analysis import (
    get_average_for_ratio,
    get_best_ratio,
)
from controllers.trading.fetchers.wrapper import get_historical_data
from algorithems.data_transform import get_extremums
from models.evaluation import Evaluation, EvaluationResults
from logger.logger import logger
from models.trading import GroupRatio
from utils.math_utils import D


actions_file_name = "data/actions.json"


def get_json_hash() -> str:
    with open(actions_file_name) as actions:
        return str(
            int(hashlib.sha1((actions.read()).encode("utf-8")).hexdigest(), 16)
            % (10**8)
        )
