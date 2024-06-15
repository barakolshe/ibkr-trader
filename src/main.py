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
    time_limit = 60
    target_profit = D("0.25")
    stop_loss = D("-0.085")

    server_queue = Queue[Stock]()
    server_thread = Thread(target=listen_for_stocks, args=(server_queue,), daemon=True)
    server_thread.start()

    time.sleep(2)

    trader_kill_event = threading.Event()
    trader = Trader(
        trader_kill_event,
        server_queue,
    )
    trader_thread = Thread(
        target=trader.main_loop,
        args=(target_profit, stop_loss, time_limit),
        daemon=True,
    )
    trader_thread.start()

    wait_for_kill_all_command()
    logger.info("Sending exit signal")
    trader_kill_event.set()
    trader_thread.join()
    logger.info("Exiting")


def get_results(
    evaluations: list[Evaluation],
    path: str,
    max_time_limit: Optional[int] = None,
    target_profit: Optional[Decimal] = None,
    stop_loss: Optional[Decimal] = None,
) -> None:
    results: list[tuple[list[EvaluationResults], GroupRatio]] = []
    time_limits_array = (
        [max_time_limit] if max_time_limit is not None else range(10, 120, 10)
    )
    for time_limit in time_limits_array:
        curr_result = iterate_evaluations(
            evaluations,
            time_limit,
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
        print(f"Saved to {path}")


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


def get_results_filename(
    max_time_limit: Optional[int],
    target_profit: Optional[Decimal],
    stop_loss: Optional[Decimal],
) -> str:
    file_name = f"results/{get_json_hash()}"
    if max_time_limit is not None:
        file_name += f"_{max_time_limit}"
    if target_profit is not None:
        file_name += f"_{target_profit}"
    if stop_loss is not None:
        file_name += f"_{stop_loss}"

    return file_name


def test_stocks() -> None:
    delay = 1
    time_limit = 60
    target_profit = D("0.25")
    stop_loss = D("-0.085")

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
    directory_path = get_results_filename(time_limit, target_profit, stop_loss)
    if not os.path.exists(directory_path):
        os.mkdir(directory_path)
    get_results(
        target_evaluations,
        f"{directory_path}/Target.pdf",
        time_limit,
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
    main()
