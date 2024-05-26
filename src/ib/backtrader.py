from __future__ import absolute_import, division, print_function, unicode_literals

import datetime  # For datetime objects
import os.path  # To manage paths
import sys  # To find out the script name (in argv[0])

# Import the backtrader platform
import backtrader as bt
from pandas import DataFrame


# Create a Stratey
class TestStrategy(bt.Strategy):

    def log(self, txt: str, dt: DataFrame = None) -> None:
        """Logging function for this strategy"""
        dt = dt or self.datas[0].datetime.date(0)
        print("%s, %s" % (dt.isoformat(), txt))

    def __init__(self) -> None:
        # Keep a reference to the "close" line in the data[0] dataseries
        self.dataclose = self.datas[0].close

    def next(self) -> None:
        # Simply log the closing price of the series from the reference
        self.log("Close, %.2f" % self.dataclose[0])


def foo() -> None:
    # Create a cerebro entity
    cerebro = bt.Cerebro()

    # Add a strategy
    cerebro.addstrategy(TestStrategy)

    # Create a Data Feed
    data = bt.feeds.YahooFinanceData(
        dataname=action.symbol,
        fromdate=datetime.datetime(2024, 5, 14),  # Adjust start date as needed
        todate=datetime.datetime(2024, 5, 16),  # Adjust end date as needed
        timeframe=bt.TimeFrame.Minutes,
        reverse=False,
    )

    # Add the Data Feed to Cerebro
    cerebro.adddata(data)

    # Set our desired cash start
    cerebro.broker.setcash(100000.0)

    # Print out the starting conditions
    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())

    # Run over everything
    cerebro.run()

    # Print out the final result
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())
