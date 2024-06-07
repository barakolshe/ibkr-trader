from datetime import timedelta, datetime
from queue import Queue
from threading import Thread, Event
from typing import Any, Optional
import backtrader as bt
from openai import BaseModel
from pandas import DataFrame
from pydantic import ConfigDict
import arrow

from controllers.trading.mock_broker import MockBroker
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
    add_divisor_event: Event
    divisor_queue: Queue[int]
    in_position_event: Event
    test_next_tick_queue: Queue[Queue[Any]]

    # debugging
    df: DataFrame


TARGET_PROFIT = D("0.4990")
STOP_LOSS = D("-0.10")
MAX_TIME = timedelta(minutes=57)


class Trader:
    app: IBapi
    trade_queue: Queue[Stock]
    kill_event: Event
    mock_broker: MockBroker

    open_strategies: list[StrategyManager] = []

    def __init__(
        self,
        app: IBapi,
        trade_queue: Queue[Stock],
        kill_event: Event,
    ) -> None:
        self.app = app
        self.trade_queue = trade_queue
        self.kill_event = kill_event
        self.mock_broker = MockBroker()

    def run_cerebro(self, df: DataFrame, strategy: bt.Strategy) -> Thread:
        cerebro = bt.Cerebro()
        cerebro.broker.set_cash(self.mock_broker.get_cash())
        cerebro.addstrategy(strategy)
        datafeed = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(datafeed)
        thread = Thread(target=cerebro.run)
        thread.start()
        return thread

    def create_strategy(
        self,
        symbol: str,
        df: DataFrame,
        event_timestamp: datetime,
        curr_datetime: Optional[datetime] = None,
    ) -> None:
        add_divisor_event = Event()
        divisor_queue = Queue[int]()
        in_position_event = Event()
        test_next_tick_queue = Queue[Queue[Any]]()

        strategy = strategy_factory(
            TARGET_PROFIT,
            STOP_LOSS,
            MAX_TIME,
            symbol,
            event_timestamp,
            add_divisor_event,
            divisor_queue,
            len(self.open_strategies) + 1,
            in_position_event,
            self.mock_broker,
            test_next_tick_queue,
            curr_datetime,
        )
        thread = self.run_cerebro(df, strategy)
        self.open_strategies.append(
            StrategyManager(
                strategy=strategy,
                thread=thread,
                add_divisor_event=add_divisor_event,
                divisor_queue=divisor_queue,
                in_position_event=in_position_event,
                test_next_tick_queue=test_next_tick_queue,
                df=df,
            )
        )

    def main_loop(self) -> None:
        while True:
            stocks = [self.trade_queue.get()]

            # Waiting for existing strategies to close positions
            strategy_on = True
            while strategy_on:
                for strategy_manager in self.open_strategies:
                    if strategy_manager.in_position_event.is_set():
                        strategy_manager.thread.join()
                        self.open_strategies.remove(strategy_manager)
                        break
                strategy_on = False

            if self.kill_event.is_set():
                return

            # Getting all the new stocks
            while not self.trade_queue.empty():
                stocks.append(self.trade_queue.get())

            # Filtering existing stocks that already have strategies
            existing_symbols: list[str] = [
                strategy_manager.strategy.symbol
                for strategy_manager in self.open_strategies
            ]
            stocks = [stock for stock in stocks if stock.symbol not in existing_symbols]

            # Adding divisors for existing strategies
            for strategy_manager in self.open_strategies:
                strategy_manager.add_divisor_event.set()
                strategy_manager.divisor_queue.put(
                    len(self.open_strategies) + len(stocks)
                )

            # Creating new strategies for new stocks
            for stock in stocks:
                self.create_strategy(
                    stock.symbol, DataFrame(), stock.article.datetime
                )  # TODO: Change this

    def main_loop_test(self, evaluations_results: list[TestEvaluationResults]) -> None:
        start_date = min(
            [result.evaluation.timestamp for result in evaluations_results]
        )
        end_date = max([result.evaluation.timestamp for result in evaluations_results])
        curr_date = start_date
        while curr_date < end_date:
            # Telling strategies to continue and waiting for their tick to end
            for strategy_manager in self.open_strategies:
                response_queue = Queue[Any]()
                strategy_manager.test_next_tick_queue.put(response_queue)
                try:
                    response_queue.get(timeout=1)
                except:
                    if not strategy_manager.thread.is_alive():
                        self.open_strategies.remove(strategy_manager)

            # Checking if any new stock should be added
            if any(
                [
                    strategy_manager.in_position_event.is_set()
                    for strategy_manager in self.open_strategies
                ]
            ):
                continue

            # Adding new stocks to the strategies
            for evaluation_result in evaluations_results:
                existing_symbols = [
                    strategy_manager.strategy.symbol
                    for strategy_manager in self.open_strategies
                ]
                if (
                    evaluation_result.df.index[0]
                    <= curr_date
                    <= evaluation_result.df.index[-1]
                    and evaluation_result.evaluation.symbol not in existing_symbols
                ):
                    self.create_strategy(
                        evaluation_result.evaluation.symbol,
                        evaluation_result.df,
                        evaluation_result.evaluation.timestamp,
                        curr_date,
                    )

            # Incrementing curr date by 1 minute
            curr_date += timedelta(minutes=1)
        print("Cash:", self.mock_broker.get_cash())

    def test_strategy(
        self,
        evaluation_results: list[TestEvaluationResults],
    ) -> None:
        results: list[dict[str, float]] = []

        cash: float = 10000
        for evaluation_result in evaluation_results:
            strategy = strategy_factory(
                TARGET_PROFIT,
                STOP_LOSS,
                timedelta(hours=1),
                evaluation_result.evaluation.symbol,
                evaluation_result.evaluation.timestamp,
                Event(),
                Queue[int](),
                1,
                Event(),
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
