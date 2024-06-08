import logging
from logging.handlers import RotatingFileHandler
import os
import sys

from discord_webhook import DiscordWebhook

from consts.data_consts import BACKUP_COUNT, LOG_FILE_PATH, ROTATING_FILE_MAX_SIZE


class DiscordHandler(logging.StreamHandler):  # type: ignore
    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        webhook_url = os.environ.get("DISCORD_WEBHOOK")
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK environment variable is not set")
        discord_webhook = DiscordWebhook(
            url=webhook_url,
            content=message[0:1900],
        )
        discord_webhook.execute()


logger = logging.getLogger(__name__)
print("name:", __name__)
logger.setLevel(logging.INFO)
# formatter = logging.Formatter(
#     "%(asctime)s | %(threadName)s | %(levelname)s | %(message)s"
# )
formatter = logging.Formatter("%(message)s")

file_handler = RotatingFileHandler(
    LOG_FILE_PATH, maxBytes=ROTATING_FILE_MAX_SIZE, backupCount=BACKUP_COUNT
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(formatter)

discord_handler = DiscordHandler()
discord_handler.setLevel(logging.ERROR)
discord_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stdout_handler)
logger.addHandler(discord_handler)
