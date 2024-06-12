from decimal import Decimal
import os
from queue import Queue
import threading
from typing import Any, Optional
import time
from threading import Thread

from controllers.evaluation.backtrade import (
    get_evaluations,
    get_json_hash,
    backtrade,
)
from controllers.evaluation.evaluate import iterate_evaluations
from controllers.graphs.graph import save_results_to_graph_file
from controllers.trading.listener import listen_for_stocks
from controllers.trading.trader import Trader
from integrations.cloud.s3 import wait_for_kill_all_command
from models.evaluation import Evaluation, EvaluationResults
from models.trading import GroupRatio, Stock
from logger.logger import logger
from utils.math_utils import D


def main() -> None:
    server_queue = Queue[Stock]()
    server_thread = Thread(target=listen_for_stocks, args=(server_queue,), daemon=True)
    server_thread.start()

    time.sleep(2)

    trader_kill_event = threading.Event()
    trader = Trader(
        trader_kill_event,
        server_queue,
    )
    trader_thread = Thread(target=trader.main_loop, daemon=True)
    trader_thread.start()

    wait_for_kill_all_command()
    logger.info("Sending exit signal")
    trader_kill_event.set()
    trader_thread.join()


def get_results(
    evaluations: list[Evaluation],
    path: str,
    max_time_limit: int = 60,
    target_profit: Optional[Decimal] = None,
    stop_loss: Optional[Decimal] = None,
) -> None:
    results: list[tuple[list[EvaluationResults], GroupRatio]] = []
    # for time_limit in range(max_time_limit):
    curr_result = iterate_evaluations(
        evaluations,
        60,
        target_profit,
        stop_loss,
    )
    if curr_result is not None:
        results.append(curr_result)
    if len(results) == 0:
        return
    best: tuple[list[EvaluationResults], GroupRatio] = max(
        results, key=lambda result: result[1].average
    )
    if best:
        save_results_to_graph_file(
            best[1],
            best[0],
            best[0][0].duration,
            path,
        )


def trade_with_backtrader() -> None:
    delay = 1
    time_limit = 60
    target_profit = D("0.4980")
    stop_loss = D("-0.1")

    evaluations = get_evaluations(delay)

    target_evaluations = [
        evaluation for evaluation in evaluations if evaluation.is_target()
    ]

    backtrade(
        target_evaluations,
        time_limit,
        target_profit,
        stop_loss,
    )


def test_stocks() -> None:
    delay = 1
    max_time_limit = 60
    target_profit = D("0.4980")
    stop_loss = D("-0.05")

    evaluations = get_evaluations(delay)
    json_hash = get_json_hash()

    evaluations_analysis_kill_queue = Queue[Any]()

    target_evaluations = [
        evaluation for evaluation in evaluations if evaluation.is_target()
    ]
    acquirer_evaluations = [
        evaluation for evaluation in evaluations if evaluation.is_acquirer()
    ]
    merging_evaluations = [
        evaluation for evaluation in evaluations if evaluation.is_merging()
    ]
    directory_path = (
        f"{json_hash}_{delay}_{max_time_limit}"
        if max_time_limit is None or stop_loss is None
        else f"{json_hash}_{delay}_{max_time_limit}_{target_profit}_{stop_loss}"
    )
    if not os.path.exists(directory_path):
        os.mkdir(directory_path)
    get_results(
        target_evaluations,
        f"{directory_path}/Target.pdf",
        max_time_limit,
        target_profit,
        stop_loss,
    )

    # get_results(
    #     acquirer_evaluations,
    #     f"{directory_path}/Acquirer.pdf",
    #     max_time_limit,
    #     target_profit,
    #     stop_loss,
    # )

    # get_results(
    #     merging_evaluations,
    #     f"{directory_path}/Merging.pdf",
    #     max_time_limit,
    #     target_profit,
    #     stop_loss,
    # )


if __name__ == "__main__":
    test_stocks()
