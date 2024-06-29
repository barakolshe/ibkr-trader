# type: ignore
import backtrader as bt


class CustomRSI(bt.Indicator):
    lines = ("rsi",)
    params = (("rsi_period", 14),)

    def __init__(self):
        self.data_close = self.data.close
        self.previous_close = self.data_close(-1)
        self.delta = self.data_close - self.previous_close

        gain = bt.If(self.delta > 0, self.delta, 0.0)
        loss = bt.If(self.delta < 0, -self.delta, 0.0)

        avg_gain = bt.indicators.SimpleMovingAverage(
            gain, period=self.params.rsi_period
        )
        avg_loss = bt.indicators.SimpleMovingAverage(
            loss, period=self.params.rsi_period
        )

        rs = bt.DivByZero(avg_gain, avg_loss, zero=100.0)

        self.lines.rsi = 100.0 - (100.0 / (1.0 + rs))
