from datetime import timedelta, datetime
from queue import Queue
from threading import Thread, Event
from turtle import position
from typing import Any, Literal, Optional, Union
import backtrader as bt
from openai import BaseModel
from pandas import DataFrame
from pydantic import ConfigDict
import arrow

from controllers.trading.mock_broker import MockBroker
from controllers.trading.positions_monitor import PositionsManager
from controllers.trading.strategy import strategy_factory
from ib.app import IBapi  # type: ignore
from ib.wrapper import complete_missing_values, get_historical_data
from models.evaluation import Evaluation, EvaluationResults, TestEvaluationResults
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


TARGET_PROFIT = D("0.4990")
STOP_LOSS = D("-0.10")
MAX_TIME = timedelta(minutes=57)


class Trader:
    app: IBapi
    trade_queue: Queue[Stock]
    kill_event: Event
    mock_broker_queue: Queue[tuple[str, Any]]

    positions_queue: Queue[tuple[str, Any]]
    positions_manager: PositionsManager

    def __init__(
        self,
        app: IBapi,
        trade_queue: Queue[Stock],
        kill_event: Event,
    ) -> None:
        self.app = app
        self.trade_queue = trade_queue
        self.kill_event = kill_event
        self.positions_queue = Queue[tuple[str, Any]]()
        self.positions_manager = PositionsManager(self.positions_queue)
        self.threads: list[tuple[Thread, Queue[tuple[Queue[Any], datetime]]]] = []
        thread = Thread(target=self.positions_manager.main_loop, daemon=True)
        thread.start()
        self.mock_broker_queue = Queue[tuple[str, Any]]()
        mock_broker = MockBroker(self.mock_broker_queue)
        mock_broker_thread = Thread(target=mock_broker.main_loop, daemon=True)
        mock_broker_thread.start()

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

    def create_strategy(
        self,
        symbol: str,
        df: DataFrame,
        event_timestamp: datetime,
        type: Literal["REAL", "TEST_REAL_TIME", "TEST"],
        curr_datetime: Optional[datetime] = None,
    ) -> None:
        test_next_tick_queue = Queue[tuple[Queue[Any], datetime]]()
        strategy = strategy_factory(
            TARGET_PROFIT,
            STOP_LOSS,
            MAX_TIME,
            symbol,
            event_timestamp,
            type,
            self.positions_queue,
            self.mock_broker_queue,
            test_next_tick_queue,
            curr_datetime,
        )
        thread = self.run_cerebro(df, strategy)
        self.threads.append((thread, test_next_tick_queue))

    def get_existing_strategies(self) -> list[Any]:
        return_queue = Queue[list[Any]]()
        self.positions_queue.put(("GET_STRATEGIES", return_queue))
        existing_strategies = return_queue.get()

        return existing_strategies

    def main_loop(self) -> None:
        while True:
            stock = self.trade_queue.get()

            if self.kill_event.is_set():
                return

            existing_strategies = self.get_existing_strategies()

            # Filtering existing stocks that already have strategies
            existing_symbols: list[str] = [
                strategy.symbol for strategy in existing_strategies
            ]
            if stock.symbol in existing_symbols:
                continue

            self.create_strategy(
                stock.symbol, DataFrame(), stock.article.datetime, "REAL"
            )

    def main_loop_test(self, evaluations_results: list[TestEvaluationResults]) -> None:
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
                        curr_date,
                    )
                    evaluations_results.remove(evaluation_result)

            for thread, test_next_tick_queue in self.threads:
                response_queue = Queue[Any]()
                test_next_tick_queue.put((response_queue, curr_date))
                try:
                    response_queue.get(timeout=0.5)
                except:
                    if not thread.is_alive():
                        self.threads.remove((thread, test_next_tick_queue))

            # Incrementing curr date by 1 minute
            curr_date += timedelta(minutes=1)

    def test_strategy(
        self,
        evaluation_results: list[TestEvaluationResults],
    ) -> None:
        cash: float = 10000
        for evaluation_result in evaluation_results:
            strategy = strategy_factory(
                TARGET_PROFIT,
                STOP_LOSS,
                timedelta(hours=1),
                evaluation_result.evaluation.symbol,
                evaluation_result.evaluation.timestamp,
                "TEST",
                self.positions_queue,
            )
            cerebro = bt.Cerebro()
            cerebro.broker.setcash(100000.0)
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
                "target_profit": float(TARGET_PROFIT),
                "stop_loss": float(STOP_LOSS),
            }
        )
