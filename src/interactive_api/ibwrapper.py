from datetime import datetime
from decimal import Decimal
from queue import Queue
from typing import Any, Optional
import arrow
from ibapi.contract import Contract
from pandas import DataFrame

from consts.time_consts import (
    DATETIME_FORMATTING,
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

    def get_historical_data(self, evaluation: Evaluation, date: datetime) -> Queue[Any]:
        logger.info(f"Getting historical data for: {evaluation.ticker}")
        contract = self.get_contract(evaluation.ticker, exchange=evaluation.exchange)

        endDate = f"{arrow.get(date, tzinfo=TIMEZONE).replace(hour=16, minute=0, second=0).format(DATETIME_FORMATTING)} {TIMEZONE}"
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

    def get_live_data(self, evaluation: Evaluation) -> Queue[Any]:
        logger.info(f"Getting live data for: {evaluation.ticker}")
        contract = self.get_contract(evaluation.ticker)

        queue = self.app.req_live_data(
            contract,
            "TRADES",  # what to show
            False,
            [],
        )

        return queue

    def get_account_usd_blocking(self) -> float:
        queue = self.app.req_account_summary("All", "$LEDGER")
        usd: float = -1
        response: Any = ""
        while response is not None:
            response = queue.get()
            if response is None:
                break
            if response[0] == "CashBalance":
                usd = response[1]

        if usd == -1:
            raise ValueError("Error getting account USD")
        return float(usd)

    def get_contract(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ) -> Contract:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency

        return contract

    def get_min_tick_blocking(self, evaluation: Evaluation) -> Optional[Decimal]:
        contract = self.get_contract(evaluation.ticker, exchange=evaluation.exchange)
        queue = self.app.req_contract_details(contract)
        min_tick: Optional[Decimal] = None
        response: Any = ""
        while response is not None:
            response = queue.get()
            if response is None:
                break
            min_tick = D(response.minTick)

        return min_tick
