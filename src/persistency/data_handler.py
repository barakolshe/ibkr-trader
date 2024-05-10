import json
import os
import json

from consts.data_consts import GROUPS_FILE_PATH
from logger.logger import logger
from models.trading import GroupRatio


def save_groups_to_file(groups: list[GroupRatio]) -> None:
    logger.info("Saving groups to file")
    groups_json = json.dumps([group.get_json() for group in groups])
    print(os.getcwd())
    with open(GROUPS_FILE_PATH, "w") as groups_file:
        groups_file.write(groups_json)


def load_groups_from_file() -> list[GroupRatio]:
    logger.info("Loading stocks json")
    path = os.environ.get(GROUPS_FILE_PATH)
    if not path:
        raise ValueError("GROUPS_FILE_PATH environment variable not set")
    with open(path, "r") as stocks_file:
        return [
            GroupRatio(
                score_range=group_ratio_json["score_range"],
                target_profit=group_ratio_json["target_profit"],
                stop_loss=group_ratio_json["stop_loss"],
                average=group_ratio_json["average"],
                urls=group_ratio_json["urls"],
            )
            for group_ratio_json in json.load(stocks_file)
        ]
