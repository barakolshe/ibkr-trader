from utils.time_utils import hours_to_seconds, minutes_to_seconds


TIMEZONE = "US/Eastern"
DATETIME_FORMATTING = "YYYYMMDD HH:mm:ss"
AWARE_DATETIME_FORMATTING = f"{DATETIME_FORMATTING} ZZZ"

MINUTES_FROM_START = 60
SECONDS_FROM_END = minutes_to_seconds(MINUTES_FROM_START)
SAFETY_DAY_GAP = 1
BAR_SIZE_MINUTES = 1
BAR_SIZE_SECONDS = BAR_SIZE_MINUTES * 60

INFO_SCRAPE_DELAY_MINUTES = 1

ALPACA_TIME_FORMAT = "YYYY-MM-DDTHH:mm:ss-04:00"
