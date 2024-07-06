from datetime import timedelta, datetime
from random import randint
from sre_constants import LITERAL
from typing import Any, Literal, Optional
import arrow
import backtrader as bt

from atreyu_backtrader_api import IBStore
from pandas import DataFrame
import pandas as pd
from controllers.trading.commision import IBKRCommission  # type: ignore
from controllers.trading.fetchers.wrapper import get_historical_data
from controllers.trading.new_strategy import NewTrader
from models.evaluation import Evaluation
from logger.logger import logger, log_important


class BaseTrader:

    def add_datafeeds(
        self, filtered_evaluations: list[Evaluation], date: datetime
    ) -> None:
        if not self.store or not self.cerebro:
            raise ValueError("Store or Cerebro not initialized")
        for evaluation in filtered_evaluations:
            ib_data = self.store.getdata(
                name=evaluation.symbol,  # Data name
                dataname=evaluation.symbol,  # Symbol name
                secType="STK",  # SecurityType is STOCK
                exchange="SMART",  # Trading exchange IB's SMART exchange
                currency="USD",  # Currency of SecurityType
                fromdate=arrow.get(date).datetime.replace(tzinfo=None),
                todate=arrow.get(date).shift(days=1).datetime.replace(tzinfo=None),
                what="TRADES",
                timeframe=bt.TimeFrame.Minutes,
                historical=True,
                rtbar=True,
            )

            self.cerebro.resampledata(
                ib_data, timeframe=bt.TimeFrame.Minutes, compression=1
            )

            log_important(
                f"Adding data for {evaluation.symbol} {arrow.get(date).format('YYYY-MM-DD')}",
                "info",
            )

    def add_commission(self) -> None:
        raise NotImplementedError

    def add_filler(self) -> None:
        raise NotImplementedError

    def add_broker(self, cash: float) -> None:
        raise NotImplementedError

    def wrap_up(self) -> None:
        raise NotImplementedError

    def test_strategy(
        self,
        evaluations: list[Evaluation],
    ) -> None:
        cash = 40000
        # min_date = min(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])
        min_date = arrow.get(evaluations[0].timestamp).replace(month=6, day=1)
        max_date = max(*[arrow.get(evaluation.timestamp) for evaluation in evaluations])

        logger.info(f"{min_date}  -   {max_date}")

        date_range = [
            min_date.datetime + timedelta(days=delta)
            for delta in range((max_date.datetime - min_date.datetime).days + 1)
        ]

        log_important(f"cash: {cash}", "info")
        waiting_stocks = []
        for date in date_range:
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
            trader = NewTrader(date, is_testing=True)
            trader.main_loop(filtered_evaluations)

            log_important(f"cash: {cash}", "info")


class TestTrader(BaseTrader):

    def add_commission(self) -> None:
        if not self.cerebro:
            raise ValueError("Cerebro not initialized")
        comminfo = IBKRCommission()  # 0.5%
        self.cerebro.broker.addcommissioninfo(comminfo)

    def add_filler(self) -> None:
        if not self.cerebro:
            raise ValueError("Cerebro not initialized")
        self.cerebro.broker.set_filler(bt.broker.filler.FixedSize())

    def add_broker(self, cash: float) -> None:
        if not self.cerebro:
            raise ValueError("Store or Cerebro not initialized")
        self.cerebro.broker.setcash(cash)

    def wrap_up(self) -> None:
        if not self.store:
            raise ValueError("Store not initialized")
        self.store.getbroker().stop(should_really_stop=True)


class IBKRTrader(BaseTrader):
    def add_commission(self) -> None:
        pass

    def add_filler(self) -> None:
        pass

    def add_broker(self, cash: float) -> None:
        if not self.store or not self.cerebro:
            raise ValueError("Store or Cerebro not initialized")
        self.cerebro.setbroker(self.store.getbroker())
