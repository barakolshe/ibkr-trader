import os
from queue import Queue
from typing import Any, Optional
import time
from threading import Thread

from controllers.evaluation.evaluate import get_evaluations, iterate_evaluations
from controllers.trading.listener import listen_for_stocks
from controllers.trading.trader import Trader
from ib.app import IBapi  # type: ignore
from integrations.cloud.s3 import wait_for_kill_all_command
from models.trading import Stock
from logger.logger import logger


def main() -> None:
    evaluations = get_evaluations()
    app_queue = Queue[Any]()
    app = IBapi(app_queue)
    app.connect("127.0.0.1", 7497, 1)
    ib_app_thread = Thread(target=app.run, daemon=True)
    ib_app_thread.start()

    time.sleep(2)
    server_kill_queue = Queue[Any]()
    server_queue = Queue[Optional[Stock]]()
    server_thread = Thread(
        target=listen_for_stocks, args=(server_queue, server_kill_queue), daemon=True
    )
    server_thread.start()

    time.sleep(2)

    if os.environ.get("TRADE") == "True":
        trader_kill_queue = Queue[Any]()
        trader = Trader(app, server_queue, app_queue, trader_kill_queue)
        trader_thread = Thread(target=trader.main_loop, daemon=True)
        trader_thread.start()

    evaluations_analysis_kill_queue = Queue[Any]()
    evaluations_analysis_thread = Thread(
        target=iterate_evaluations,
        args=(app, evaluations, app_queue, evaluations_analysis_kill_queue),
        daemon=True,
    )
    evaluations_analysis_thread.start()

    wait_for_kill_all_command()
    logger.info("Sending exit signal")
    if os.environ.get("TRADE") == "True":
        trader_kill_queue.put(None)
        trader_thread.join()

    server_kill_queue.put(None)
    server_thread.join()
    evaluations_analysis_kill_queue.put(None)
    evaluations_analysis_thread.join()
    app.disconnect()
    ib_app_thread.join()


def test_stocks() -> None:
    evaluations = get_evaluations()
    app_queue = Queue[Any]()
    app = IBapi(app_queue)
    app.connect("127.0.0.1", 7497, 1)
    ib_app_thread = Thread(target=app.run, daemon=True)
    ib_app_thread.start()

    time.sleep(2)

    evaluations_analysis_kill_queue = Queue[Any]()
    # evaluations_analysis_thread = Thread(
    #     target=,
    #     args=(app, evaluations, app_queue, evaluations_analysis_kill_queue),
    #     daemon=True,
    # )
    # evaluations_analysis_thread.start()

    # wait_for_kill_all_command()
    # logger.info("Sending exit signal")
    # evaluations_analysis_kill_queue.put(None)
    # evaluations_analysis_thread.join()

    iterate_evaluations(app, evaluations, app_queue, evaluations_analysis_kill_queue)
    app.disconnect()
    ib_app_thread.join()


if __name__ == "__main__":
    test_stocks()
