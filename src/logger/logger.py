import logging
import sys

# from discord_webhook import DiscordWebhook

# class DiscordHandler(logging.StreamHandler):  # type: ignore
#     def emit(self, record: logging.LogRecord) -> None:
#         message = self.format(record)
#         discord_webhook = DiscordWebhook(
#             url=DISCORD_URL,
#             content=message[0:1900],
#         )
#         discord_webhook.execute()


logger = logging.getLogger(__name__)
print("name:", __name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s | %(threadName)s | %(levelname)s | %(message)s"
)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.setFormatter(formatter)

logger.addHandler(stdout_handler)
