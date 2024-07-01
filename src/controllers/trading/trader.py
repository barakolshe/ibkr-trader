from datetime import timedelta, datetime
from random import randint
from sre_constants import LITERAL
from typing import Literal, Optional
import arrow
import backtrader as bt

from atreyu_backtrader_api import IBStore
from controllers.trading.commision import IBKRCommission  # type: ignore
from controllers.trading.fetchers.wrapper import get_historical_data
from controllers.trading.strategy import StrategyType, strategy_factory
from models.evaluation import Evaluation
from logger.logger import logger, log_important


class BaseTrader:
    store: Optional[IBStore] = None
    cerebro: Optional[bt.Cerebro] = None

    def get_strategy_type(self) -> StrategyType:
        raise NotImplementedError

    def create_store(self) -> None:
        self.store = IBStore(host="127.0.0.1", port=4002, clientId=35, _debug=True)

    def add_datafeeds(
        self, filtered_evaluations: list[Evaluation], date: datetime
    ) -> None:
        if not self.store or not self.cerebro:
            raise ValueError("Store or Cerebro not initialized")
        for evaluation in filtered_evaluations:
            data = self.store.getdata(
                name=evaluation.symbol,  # Data name
                dataname=evaluation.symbol,  # Symbol name
                secType="STK",  # SecurityType is STOCK
                exchange="SMART",  # Trading exchange IB's SMART exchange
                currency="USD",  # Currency of SecurityType
                fromdate=arrow.get(
                    arrow.get(date).shift(days=-1).date()
                ).datetime.replace(tzinfo=None),
                todate=arrow.get(arrow.get(date).shift(days=1).date()).datetime.replace(
                    tzinfo=None
                ),
                what="TRADES",
                timeframe=bt.TimeFrame.Minutes,
                historical=True,
                rtbar=True,
            )
            self.cerebro.adddata(data)
            self.cerebro.resampledata(
                data, timeframe=bt.TimeFrame.Minutes, compression=3
            )
            self.cerebro.resampledata(
                data, timeframe=bt.TimeFrame.Minutes, compression=5
            )
            log_important(
                f"Adding data for {evaluation.symbol} {arrow.get(date).format('YYYY-MM-DD')}",
                "info",
            )

    def add_commission(self) -> None:
        pass

    def add_filler(self) -> None:
        pass

    def add_broker(self) -> None:
        if not self.store or not self.cerebro:
            raise ValueError("Store or Cerebro not initialized")
        self.cerebro.setbroker(self.store.getbroker())

    def wrap_up(self) -> None:
        if not self.store:
            raise ValueError("Store not initialized")
        self.store.getbroker().stop()

    def test_strategy(
        self,
        evaluations: list[Evaluation],
    ) -> None:
        # min_date = min(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])
        min_date = arrow.get(evaluations[0].timestamp).replace(month=6, day=1)
        max_date = max(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])

        logger.info(f"{min_date}  -   {max_date}")

        date_range = [
            min_date.datetime + timedelta(days=delta)
            for delta in range((max_date.datetime - min_date.datetime).days + 1)
        ]

        self.create_store()
        if not self.store:
            raise ValueError("Store not initialized")
        log_important(f"cash: {self.store.getbroker()}", "info")
        waiting_stocks = []
        for date in date_range:
            self.cerebro = bt.Cerebro()
            self.add_broker()
            filtered_evaluations = [
                evaluation
                for evaluation in evaluations
                if arrow.get(date).date() == arrow.get(evaluation.timestamp).date()
            ]
            if date.weekday() == 5 or date.weekday() == 6:
                waiting_stocks.extend(filtered_evaluations)
                continue
            filtered_evaluations.extend(waiting_stocks)
            waiting_stocks = []
            if len(filtered_evaluations) == 0:
                continue
            self.add_datafeeds(filtered_evaluations, date)
            strategy = strategy_factory(
                [evaluation.symbol for evaluation in filtered_evaluations],
                arrow.get(date).datetime,
                self.get_strategy_type(),
            )
            self.cerebro.addstrategy(strategy)

            self.cerebro.run()

            log_important(f"cash: {self.store.getbroker()}", "info")


class TestTrader(BaseTrader):
    def get_strategy_type(self) -> StrategyType:
        return StrategyType.TEST


class LiveTrader(BaseTrader):
    def get_strategy_type(self) -> StrategyType:
        return StrategyType.REAL
