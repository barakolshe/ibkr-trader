from utils.time_utils import hours_to_seconds


TIMEZONE = "US/Eastern"
DATETIME_FORMATTING = "YYYYMMDD HH:mm:ss"
AWARE_DATETIME_FORMATTING = f"{DATETIME_FORMATTING} ZZZ"

HOURS_FROM_START = 1
SECONDS_FROM_END = hours_to_seconds(HOURS_FROM_START)
BAR_SIZE_SECONDS = 120
