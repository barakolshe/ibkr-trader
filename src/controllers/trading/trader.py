from datetime import timedelta, datetime
from queue import Queue
from random import randint
from threading import Thread, Event
from typing import Any, Optional
import arrow
import backtrader as bt
from pandas import DataFrame
from pydantic import ConfigDict, BaseModel
from ateryu_backtrader_api import IBData

from atreyu_backtrader_api import IBStore
import yfinance
from consts.time_consts import TIMEZONE
from controllers.trading.mock_broker import MockBroker
from controllers.trading.strategy import strategy_factory
from models.evaluation import Evaluation
from models.trading import Stock
from logger.logger import logger


class StrategyManager(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    strategy: Any
    thread: Thread
    divisor_queue: Queue[int]
    in_position_event: Event
    test_next_tick_queue: Queue[tuple[Queue[Any], datetime]]

    # debugging
    df: DataFrame


class Trader:
    server_queue: Optional[Queue[Stock]] = None
    kill_event: Optional[Event] = None
    mock_broker_queue: Queue[tuple[str, Any]]
    store: bt.stores.IBStore
    threads: list[tuple[Thread, Any]]

    def __init__(
        self,
        kill_event: Optional[Event] = None,
        server_queue: Optional[Queue[Stock]] = None,
    ) -> None:
        self.server_queue = server_queue
        self.kill_event = kill_event
        self.threads = []
        self.mock_broker_queue = Queue[tuple[str, Any]]()
        mock_broker = MockBroker(self.mock_broker_queue, 5000.0)
        mock_broker_thread = Thread(target=mock_broker.main_loop, daemon=True)
        mock_broker_thread.start()
        self.store = IBStore(host="127.0.0.1", port=7497, clientId=randint(0, 100))

    def get_cash(self) -> float:
        response_queue = Queue[float]()
        self.mock_broker_queue.put(("GET", response_queue))
        return response_queue.get()

    # def main_loop(
    #     self, target_profit: Decimal, stop_loss: Decimal, max_time: int
    # ) -> None:
    #     while True:
    #         if not self.server_queue:
    #             raise Exception("Trade queue is None")
    #         try:
    #             stock = self.server_queue.get(timeout=10)
    #         except Exception as e:
    #             if self.kill_event.is_set():
    #                 self.stop_strategies()
    #                 self.store.conn.disconnect()
    #                 return
    #             continue

    #         # Filtering existing stocks that already have strategies
    #         existing_symbols: list[str] = [
    #             strategy.symbol for strategy in existing_strategies
    #         ]
    #         if stock.symbol in existing_symbols:
    #             continue

    #         try:
    #             self.create_strategy_ibkr(
    #                 stock.symbol,
    #                 stock.article.datetime,
    #                 target_profit,
    #                 stop_loss,
    #                 max_time,
    #             )
    #         except BadDataFeedException:
    #             continue

    def test_strategy(
        self,
        evaluations: list[Evaluation],
    ) -> None:
        cash: float = 5000
        min_date = min(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])
        max_date = max(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])
        min_date.replace(hour=0, minute=0, second=0)
        max_date.replace(hour=0, minute=0, second=0)

        date_range = [
            min_date.datetime + timedelta(days=delta)
            for delta in range((max_date.datetime - min_date.datetime).days + 1)
        ]
        for date in date_range:
            cerebro = bt.Cerebro()
            cerebro.broker.setcash(cash)
            filtered_evaluations = [
                evaluation
                for evaluation in evaluations
                if arrow.get(date).shift(days=-1).replace(hour=16, minute=0, second=0)
                < evaluation.timestamp
                < arrow.get(date).replace(hour=9, minute=30, second=0)
            ]
            for evaluation in filtered_evaluations:
                if (arrow.now(tz=TIMEZONE).datetime - evaluation.timestamp).days >= 40:
                    continue
                # try:
                data = yfinance.Ticker(evaluation.symbol).history(
                    start=arrow.get(date).shift(days=-1).datetime.strftime("%Y-%m-%d"),
                    end=arrow.get(date).shift(days=1).datetime.strftime("%Y-%m-%d"),
                    # auto_adjust=True,
                    interval="2m",
                )
                datafeed = bt.feeds.PandasData(dataname=data)
                # except Exception:
                #     logger.info(f"Cant get data for {evaluation.symbol}")
                #     continue
                logger.info(f"Adding data for {evaluation.symbol} {date}")
                cerebro.adddata(datafeed)
            strategy = strategy_factory(
                [evaluation.symbol for evaluation in filtered_evaluations],
                arrow.get(date).datetime,
                "TEST",
                _mock_broker_queue=self.mock_broker_queue,
            )
            cerebro.addstrategy(strategy)
            cerebro.run()
            cash = cerebro.broker.getcash()
            print(
                {
                    "cash": cash,
                }
            )

    def stop_strategies(self) -> None:
        for thread, strategy in self.threads:
            strategy.stop_run()
            thread.join()
