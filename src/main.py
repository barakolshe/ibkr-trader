from controllers.evaluation.backtrade import (
    get_evaluations,
)
from controllers.trading.trader import Trader


# def main() -> None:
#     server_queue = Queue[Stock]()
#     server_thread = Thread(target=listen_for_stocks, args=(server_queue,), daemon=True)
#     server_thread.start()

#     time.sleep(2)

#     trader_kill_event = threading.Event()
#     trader = Trader(
#         trader_kill_event,
#         server_queue,
#     )
#     trader_thread = Thread(
#         target=trader.main_loop,
#         args=(target_profit, stop_loss, time_limit),
#         daemon=True,
#     )
#     trader_thread.start()

#     wait_for_kill_all_command()
#     logger.info("Sending exit signal")
#     trader_kill_event.set()
#     trader_thread.join()
#     logger.info("Exiting")


def trade_with_backtrader() -> None:
    delay = 1

    evaluations = get_evaluations(delay)

    target_evaluations = [evaluation for evaluation in evaluations]

    trader = Trader()

    trader.test_strategy(target_evaluations)


if __name__ == "__main__":
    trade_with_backtrader()
