from decimal import Decimal
from queue import Queue
from typing import Any, Optional
import arrow
from ibapi.contract import Contract
from pandas import DataFrame

from consts.time_consts import (
    DATETIME_FORMATTING,
    SECONDS_FROM_END,
    TIMEZONE,
)
from interactive_api.app import IBapi
from models.evaluation import Evaluation
from logger.logger import logger
from utils.math_utils import D


class IBWrapper:
    app: IBapi

    def __init__(self, app: IBapi) -> None:
        self.app = app

    def get_historical_data(
        self,
        evaluation: Evaluation,
    ) -> Queue[Any]:
        logger.info(f"Getting historical data for evaluation: {evaluation}")
        contract = self.get_contract(evaluation.symbol)

        endDate = f"{arrow.get(evaluation.timestamp, TIMEZONE).replace(hour=16, minute=0, second=0).format(DATETIME_FORMATTING)} {TIMEZONE}"
        queue = self.app.req_historical_data(
            contract,
            endDate,  # end date time
            f"1 D",  # duration
            f"1 min",  # bar size
            "TRADES",  # what to show
            0,  # is regular trading hours
            1,  # format date
            False,  # keep up to date
            [],  # chart options
        )

        return queue

    def get_account_usd_blocking(self, response_queue: Queue[Any]) -> float:
        queue = self.app.req_account_summary("All", "$LEDGER")
        usd: float = -1
        response: Any = ""
        while response is not None:
            response = queue.get()
            if response is None:
                break
            if response[0] == "CashBalance":
                usd = response[1]
                break

        if usd == -1:
            raise ValueError("Error getting account USD")
        return min(float(usd), 40000)

    def get_contract(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ) -> Contract:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency

        return contract
