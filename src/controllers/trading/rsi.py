# type: ignore
class CustomRSI(bt.Indicator):
    lines = ("rsi",)

    params = (("rsi_period", 14),)

    def __init__(self):
        self.data_close = self.data.close
        self.previous_close = self.data_close(-1)
        self.delta = self.data_close - self.previous_close

        self.avg_gain = bt.indicators.SmoothedMovingAverage(
            self.delta, period=self.params.rsi_period, plot=False
        )
        self.avg_loss = bt.indicators.SmoothedMovingAverage(
            bt.indicators.Abs(self.delta), period=self.params.rsi_period, plot=False
        )

        self.rs = bt.indicators.IfElse(
            self.avg_loss == 0, 100.0, self.avg_gain / self.avg_loss
        )

        self.lines.rsi = 100.0 - (100.0 / (1.0 + self.rs))
