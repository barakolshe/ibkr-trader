from decimal import Decimal
from queue import Queue
from typing import Any, Optional
import arrow
from ibapi.contract import Contract
from pandas import DataFrame

from consts.time_consts import (
    BAR_SIZE_SECONDS,
    DATETIME_FORMATTING,
    HOURS_FROM_START,
    SECONDS_FROM_END,
    TIMEZONE,
)
from consts.trading_consts import MAX_CASH_VALUE
from ib.app import IBapi  # type: ignore
from models.evaluation import Evaluation
from logger.logger import logger
from utils.math_utils import D


def get_historical_data(
    app: IBapi,
    evaluation: Evaluation,
    response_queue: Queue[Any],
    id: Optional[int] = None,
) -> DataFrame:
    logger.info(f"Getting historical data for evaluation: {evaluation}")
    contract = Contract()
    contract.symbol = evaluation.symbol
    contract.secType = "STK"
    contract.exchange = evaluation.exchange  # TODO: change this
    contract.currency = "USD"

    endDate = f"{arrow.get(evaluation.datetime, TIMEZONE).shift(hours=HOURS_FROM_START).format(DATETIME_FORMATTING)} {TIMEZONE}"
    app.reqHistoricalData(
        app.nextValidOrderId if id is None else id,
        contract,
        endDate,  # end date time
        f"{SECONDS_FROM_END} S",  # duration
        f"{BAR_SIZE_SECONDS} secs",  # bar size
        "MIDPOINT",  # what to show
        0,  # is regular trading hours
        1,  # format date
        False,  # keep up to date
        [],  # chart options
    )
    df: DataFrame = response_queue.get()

    return df


def get_account_usd(app: IBapi, response_queue: Queue[Any]) -> Decimal:
    app.reqAccountSummary(app.nextValidOrderId, "All", "$LEDGER")
    usd: Decimal = D("-1")
    response: Any = ""
    while response is not None:
        try:
            response = response_queue.get(timeout=15)
        except:
            break
        if response is None:
            break
        if response[0] == "CashBalance":
            usd = D(response[1])

    if usd == -1:
        raise ValueError("Error getting account USD")
    return usd.min(MAX_CASH_VALUE)


def get_current_stock_price(
    app: IBapi, symbol: str, exchange: str, response_queue: Queue[Any]
) -> Optional[Decimal]:
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = "USD"
    app.reqMktData(app.nextValidOrderId, contract, "", True, False, [])
    try:
        value: Decimal = D(response_queue.get(timeout=10))
    except:
        return None
    return value


def get_contract(symbol: str, exchange: str) -> Contract:
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = "USD"
    return contract
