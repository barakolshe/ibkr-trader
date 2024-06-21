from datetime import timedelta, datetime
from decimal import Decimal
from queue import Queue
from random import randint
from threading import Thread, Event
from time import strftime
from typing import Any, Literal, Optional
import arrow
import backtrader as bt
from pandas import DataFrame
from pydantic import ConfigDict, BaseModel

from atreyu_backtrader_api import IBStore
import yfinance
from controllers.trading.mock_broker import MockBroker
from controllers.trading.positions_monitor import PositionsManager
from controllers.trading.strategy import strategy_factory
from exceptions.BadDataFeedException import BadDataFeedException
from models.evaluation import Evaluation, TestEvaluationResults
from models.trading import Stock
from utils.math_utils import D


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
    kill_event: Event
    mock_broker_queue: Queue[tuple[str, Any]]
    store: bt.stores.IBStore
    threads: list[tuple[Thread, Any]]

    def __init__(
        self,
        kill_event: Event,
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

    def run_cerebro(self, df: DataFrame, strategy: bt.Strategy) -> Thread:
        cerebro = bt.Cerebro()
        cerebro.broker.set_cash(self.get_cash())
        cerebro.addstrategy(strategy)
        datafeed = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(datafeed)
        thread = Thread(target=cerebro.run, daemon=True)
        thread.start()
        return thread

    def run_cerebro_ibkr(self, symbol: str, strategy: bt.Strategy) -> Thread:
        cerebro = bt.Cerebro()
        cerebro.setbroker(self.store.getbroker())
        cerebro.addstrategy(strategy)
        # try:
        data = self.store.getdata(
            name=symbol,  # Data name
            dataname=symbol,  # Symbol name
            secType="STK",  # SecurityType is STOCK
            exchange="SMART",  # Trading exchange IB's SMART exchange
            currency="USD",  # Currency of SecurityType
        )
        # except:
        #     logger.info(f"Bad datafeed {symbol}", exc_info=True)
        #     raise BadDataFeedException()
        cerebro.adddata(data)
        thread = Thread(target=cerebro.run, daemon=True)
        thread.start()
        return thread

    def create_strategy_ibkr(
        self,
        symbol: str,
        event_timestamp: datetime,
        target_profit: Decimal,
        stop_loss: Decimal,
        max_time: int,
    ) -> None:
        strategy = strategy_factory(
            target_profit,
            stop_loss,
            max_time,
            symbol,
            event_timestamp,
            "REAL",
        )
        thread = self.run_cerebro_ibkr(symbol, strategy)
        self.threads.append((thread, strategy))

    def create_strategy(
        self,
        symbol: str,
        df: DataFrame,
        event_timestamp: datetime,
        type: Literal["REAL", "TEST"],
        target_profit: Decimal,
        stop_loss: Decimal,
        max_time: int,
    ) -> None:
        strategy = strategy_factory(
            target_profit,
            stop_loss,
            max_time,
            symbol,
            event_timestamp,
            type,
            _mock_broker_queue=self.mock_broker_queue,
        )
        thread = self.run_cerebro(df, strategy)
        self.threads.append((thread, strategy))

    def get_existing_strategies(self) -> list[Any]:
        return_queue = Queue[list[Any]]()
        existing_strategies = return_queue.get()

        return existing_strategies

    def main_loop(
        self, target_profit: Decimal, stop_loss: Decimal, max_time: int
    ) -> None:
        while True:
            if not self.server_queue:
                raise Exception("Trade queue is None")
            try:
                stock = self.server_queue.get(timeout=10)
            except Exception as e:
                if self.kill_event.is_set():
                    self.stop_strategies()
                    self.store.conn.disconnect()
                    return
                continue

            existing_strategies = self.get_existing_strategies()

            # Filtering existing stocks that already have strategies
            existing_symbols: list[str] = [
                strategy.symbol for strategy in existing_strategies
            ]
            if stock.symbol in existing_symbols:
                continue

            try:
                self.create_strategy_ibkr(
                    stock.symbol,
                    stock.article.datetime,
                    target_profit,
                    stop_loss,
                    max_time,
                )
            except BadDataFeedException:
                continue

    def test_strategy(
        self,
        evaluations: list[Evaluation],
        target_profit: Decimal,
        stop_loss: Decimal,
        max_time: int,
    ) -> None:
        cash: float = 5000
        min_date = min(*[evaluation.timestamp.date() for evaluation in evaluations])
        max_date = max(*[evaluation.timestamp.date() for evaluation in evaluations])
        for date in range(min_date, max_date):
            cerebro = bt.Cerebro()
            cerebro.broker.setcash(5000.0)
            evaluations = [
                evaluation
                for evaluation in evaluations
                if evaluation.timestamp.date() == date
            ]
            for evaluation in evaluations:
                datafeed = bt.feeds.PandasData(
                    dataname=yfinance.download(
                        evaluation.symbol,
                        arrow.get(evaluation.timestamp)
                        .shift(days=-1)
                        .strftime("YYYY-MM-DD"),
                        arrow.get(evaluation.timestamp).strftime("YYYY-MM-DD"),
                        auto_adjust=True,
                    )
                )
                cerebro.adddata(datafeed)
            cerebro.addstrategy(strategy)
            cerebro.run()
        print(
            {
                "cash": cash,
                "target_profit": float(target_profit),
                "stop_loss": float(stop_loss),
                "max_time": max_time,
            }
        )

    def stop_strategies(self) -> None:
        for thread, strategy in self.threads:
            strategy.stop_run()
            thread.join()
