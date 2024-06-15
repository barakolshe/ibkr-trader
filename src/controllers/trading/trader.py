from datetime import timedelta, datetime
from decimal import Decimal
from queue import Queue
from random import randint
from threading import Thread, Event
from typing import Any, Literal, Optional
import backtrader as bt
from pandas import DataFrame
from pydantic import ConfigDict, BaseModel

from atreyu_backtrader_api import IBStore
from controllers.trading.mock_broker import MockBroker
from controllers.trading.positions_monitor import PositionsManager
from controllers.trading.strategy import strategy_factory
from exceptions.BadDataFeedException import BadDataFeedException
from models.evaluation import TestEvaluationResults
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
    threads: list[tuple[Thread, Optional[Queue[tuple[Queue[Any], datetime]]], Any]]
    positions_queue: Queue[tuple[str, Any]]
    positions_manager: PositionsManager

    def __init__(
        self,
        kill_event: Event,
        server_queue: Optional[Queue[Stock]] = None,
    ) -> None:
        self.server_queue = server_queue
        self.kill_event = kill_event
        self.positions_queue = Queue[tuple[str, Any]]()
        self.positions_manager = PositionsManager(self.positions_queue)
        self.threads = []
        thread = Thread(target=self.positions_manager.main_loop, daemon=True)
        thread.start()
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
            self.positions_queue,
        )
        thread = self.run_cerebro_ibkr(symbol, strategy)
        self.threads.append((thread, None, strategy))

    def create_strategy(
        self,
        symbol: str,
        df: DataFrame,
        event_timestamp: datetime,
        type: Literal["REAL", "TEST_REAL_TIME", "TEST"],
        target_profit: Decimal,
        stop_loss: Decimal,
        max_time: int,
        curr_datetime: Optional[datetime] = None,
    ) -> None:
        test_next_tick_queue = Queue[tuple[Queue[Any], datetime]]()
        strategy = strategy_factory(
            target_profit,
            stop_loss,
            max_time,
            symbol,
            event_timestamp,
            type,
            self.positions_queue,
            self.mock_broker_queue,
            test_next_tick_queue,
            curr_datetime,
        )
        thread = self.run_cerebro(df, strategy)
        self.threads.append((thread, test_next_tick_queue, strategy))

    def get_existing_strategies(self) -> list[Any]:
        return_queue = Queue[list[Any]]()
        self.positions_queue.put(("GET_STRATEGIES", return_queue))
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

    def main_loop_test(
        self,
        evaluations_results: list[TestEvaluationResults],
        target_profit: Decimal,
        stop_loss: Decimal,
        max_time: int,
    ) -> None:
        start_date = min(
            [result.evaluation.timestamp for result in evaluations_results]
        )
        end_date = max([result.evaluation.timestamp for result in evaluations_results])
        curr_date = start_date
        while curr_date < end_date:
            # Adding new stocks to the strategies
            for evaluation_result in evaluations_results:
                existing_symbols = [
                    strategy.symbol for strategy in self.get_existing_strategies()
                ]
                if (
                    min(
                        evaluation_result.df.index[0],
                        evaluation_result.evaluation.timestamp,
                    )
                    <= curr_date
                    <= evaluation_result.df.index[-1]
                    and evaluation_result.evaluation.symbol not in existing_symbols
                ):
                    self.create_strategy(
                        evaluation_result.evaluation.symbol,
                        evaluation_result.df,
                        evaluation_result.evaluation.timestamp,
                        "TEST_REAL_TIME",
                        target_profit,
                        stop_loss,
                        max_time,
                        curr_date,
                    )
                    evaluations_results.remove(evaluation_result)

            for thread, test_next_tick_queue, strategy in self.threads:
                response_queue = Queue[Any]()
                if not test_next_tick_queue:
                    raise Exception("Test next tick queue is None")
                test_next_tick_queue.put((response_queue, curr_date))
                try:
                    response_queue.get(timeout=0.5)
                except:
                    if not thread.is_alive():
                        self.threads.remove((thread, test_next_tick_queue, strategy))

            # Incrementing curr date by 1 minute
            curr_date += timedelta(minutes=1)

    def test_strategy(
        self,
        evaluation_results: list[TestEvaluationResults],
        target_profit: Decimal,
        stop_loss: Decimal,
        max_time: int,
    ) -> None:
        cash: float = 5000
        for evaluation_result in evaluation_results:
            strategy = strategy_factory(
                target_profit,
                stop_loss,
                max_time,
                evaluation_result.evaluation.symbol,
                evaluation_result.evaluation.timestamp,
                "TEST",
                self.positions_queue,
            )
            cerebro = bt.Cerebro()
            cerebro.broker.setcash(5000.0)
            cerebro.addstrategy(strategy)
            datafeed = bt.feeds.PandasData(dataname=evaluation_result.df)
            cerebro.adddata(datafeed)
            cerebro.broker.setcash(cash)
            cerebro.run()
            cash = cerebro.broker.get_cash()
            print(f"{evaluation_result.evaluation.symbol}: {(cash):.2f}")
        print(
            {
                "cash": cash,
                "target_profit": float(target_profit),
                "stop_loss": float(stop_loss),
                "max_time": max_time,
            }
        )

    def stop_strategies(self) -> None:
        for thread, _, strategy in self.threads:
            strategy.stop_run()
            thread.join()
