# type: ignore
import backtrader as bt
import ta
import pandas as pd
import numpy as np


class ADX(bt.Indicator):
    lines = ("adx", "plus_di", "minus_di")
    params = (("period", 14),)

    def __init__(self):
        self.addminperiod(self.params.period * 2)

    def next(self):
        actual_period = self.params.period * 2
        # Calculate ADX using the ta package
        adx_indicator = ta.trend.ADXIndicator(
            high=pd.Series(self.data.high.get(size=actual_period)),
            low=pd.Series(self.data.low.get(size=actual_period)),
            close=pd.Series(self.data.close.get(size=actual_period)),
            window=self.params.period,
        )

        # Assign the calculated values to the indicator lines
        self.lines.adx[0] = adx_indicator.adx().iloc[-1]
        self.lines.plus_di[0] = adx_indicator.adx_pos().iloc[-1]
        self.lines.minus_di[0] = adx_indicator.adx_neg().iloc[-1]
