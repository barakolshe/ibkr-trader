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
        adx_indicator = 

        # Assign the calculated values to the indicator lines
        self.lines.plus_di[0] = adx_indicator.adx_pos().iloc[-1]
        self.lines.minus_di[0] = adx_indicator.adx_neg().iloc[-1]
