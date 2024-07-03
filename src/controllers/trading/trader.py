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
from controllers.trading.strategy import StrategyType, strategy_factory
from models.evaluation import Evaluation
from logger.logger import logger, log_important


def datafeed_to_dataframe(datafeed: Any) -> DataFrame:
    data_points: dict[str, list[Any]] = {
        "datetime": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
        "openinterest": [],
    }

    for line in datafeed:
        data_points["datetime"].append(line.datetime.datetime(0))
        data_points["open"].append(line.open[0])
        data_points["high"].append(line.high[0])
        data_points["low"].append(line.low[0])
        data_points["close"].append(line.close[0])
        data_points["volume"].append(line.volume[0])
        data_points["openinterest"].append(line.openinterest[0])

    # Convert to a Pandas DataFrame
    df = pd.DataFrame(data_points)
    df.set_index("datetime", inplace=True)

    return df


def dataframe_to_another_timeframe(df: DataFrame, minutes: int) -> DataFrame:
    new_df = df.resample(f"{minutes}min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "openinterest": "last",
        }
    )
    return new_df


class BaseTrader:
    store: Optional[IBStore] = None
    cerebro: Optional[bt.Cerebro] = None

    def get_strategy_type(self) -> StrategyType:
        raise NotImplementedError

    def create_store(self) -> None:
        self.store = IBStore(host="127.0.0.1", port=4002, clientId=37, _debug=True)

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

            self.cerebro.adddata(ib_data)
            self.cerebro.resampledata(
                ib_data, timeframe=bt.TimeFrame.Minutes, compression=3
            )
            self.cerebro.resampledata(
                ib_data, timeframe=bt.TimeFrame.Minutes, compression=5
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

        self.create_store()
        if not self.store:
            raise ValueError("Store not initialized")
        log_important(f"cash: {cash}", "info")
        waiting_stocks = []
        for date in date_range:
            self.cerebro = bt.Cerebro()
            self.add_broker(cash)
            self.add_commission()
            self.add_filler()
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
                arrow.get(date).datetime.replace(tzinfo=None),
                self.get_strategy_type(),
            )
            self.cerebro.addstrategy(strategy)
            self.cerebro.run()
            cash = self.cerebro.broker.getcash()

            log_important(f"cash: {cash}", "info")


class TestTrader(BaseTrader):
    def get_strategy_type(self) -> StrategyType:
        return StrategyType.TEST

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


class PaperTrader(BaseTrader):
    def get_strategy_type(self) -> StrategyType:
        return StrategyType.PAPER


class LiveTrader(BaseTrader):
    def get_strategy_type(self) -> StrategyType:
        return StrategyType.LIVE
