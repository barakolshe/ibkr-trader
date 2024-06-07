from logger.logger import logger


class MockBroker:
    cash: float = 10000

    def get_cash(self) -> float:
        return self.cash

    def set_cash(self, cash: float) -> None:
        print(f"Setting cash to: {cash}")
        self.cash = cash
