# type: ignore
from decimal import Decimal
import logging
from queue import Queue
from typing import Any
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.utils import current_fn_name
import pandas as pd
import arrow
from ibapi.order import Order
from ibapi.contract import Contract
from ibapi.common import TickAttrib, TickerId
from ibapi.ticktype import TickType

from consts.time_consts import AWARE_DATETIME_FORMATTING
from logger.logger import logger
from utils.math_utils import D


class IBapi(EWrapper, EClient):  # type: ignore
    def __init__(self, queue: Queue[Any]) -> None:
        EClient.__init__(self, self)
        self.data = []
        self.df = None
        self.queue = queue
        self.nextValidOrderId = 0

    # Logging

    def insert_to_queue(self, data: Any) -> None:
        self.queue.put(data)

    def logAnswer(self, fnName, fnParams):
        if logger.isEnabledFor(logging.INFO):
            if "self" in fnParams:
                prms = dict(fnParams)
                del prms["self"]
            else:
                prms = fnParams
            logger.info("ANSWER function: %s, parameters: %s", fnName, prms)

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson="",
    ):
        """This event is called when there is an error with the
        communication or when TWS wants to send a message to the client."""
        if reqId != -1:
            self.insert_to_queue(None)
        self.logAnswer(current_fn_name(), vars())
        if advancedOrderRejectJson:
            logger.error(
                "ERROR %s %s %s %s",
                reqId,
                errorCode,
                errorString,
                advancedOrderRejectJson,
            )
        else:
            logger.error("ERROR %s %s %s", reqId, errorCode, errorString)

    def historicalData(self, reqId, bar):
        self.logAnswer(current_fn_name(), vars())
        bar_dict = vars(bar)
        bar_dict["date"] = arrow.get(
            bar_dict["date"], AWARE_DATETIME_FORMATTING
        ).datetime
        self.data.append(vars(bar))

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        self.logAnswer(current_fn_name(), vars())
        self.df = pd.DataFrame(self.data)
        self.df.set_index("date", inplace=True)
        self.insert_to_queue(self.df)
        self.df = None
        self.data = []

    def placeBracketOrder(
        self,
        parentOrderId: int,
        action: str,
        quantity: float,
        priceLimit: float,
        takeProfitLimitPrice: float,
        stopLossPrice: float,
        contract: Contract,
    ):
        self.logAnswer(current_fn_name(), vars())
        parent = Order()

        parent.orderId = parentOrderId
        parent.action = action
        parent.orderType = "LMT"
        parent.totalQuantity = quantity
        parent.lmtPrice = priceLimit
        parent.transmit = False

        takeProfit = Order()
        takeProfit.orderId = parent.orderId + 1
        takeProfit.action = "SELL" if action == "BUY" else "BUY"
        takeProfit.orderType = "LMT"
        takeProfit.totalQuantity = quantity
        takeProfit.lmtPrice = takeProfitLimitPrice
        takeProfit.parentId = parentOrderId
        takeProfit.transmit = False

        stopLoss = Order()
        stopLoss.orderId = parent.orderId + 2
        stopLoss.action = "SELL" if action == "BUY" else "BUY"
        stopLoss.orderType = "STP"
        stopLoss.auxPrice = stopLossPrice
        stopLoss.totalQuantity = quantity
        stopLoss.parentId = parentOrderId
        stopLoss.transmit = True

        bracketOrder = [parent, takeProfit, stopLoss]
        for order in bracketOrder:
            self.placeOrder(order.orderId, contract, order)

    def accountSummary(
        self, reqId: int, account: str, tag: str, value: str, currency: str
    ):
        self.logAnswer(current_fn_name(), vars())
        self.insert_to_queue((tag, value))

    def accountSummaryEnd(self, reqId: int):
        self.logAnswer(current_fn_name(), vars())
        self.insert_to_queue(None)

    # def historicalDataUpdate(self, reqId, bar):
    #     line = vars(bar)
    #     # pop date and make it the index, add rest to df
    #     # will overwrite last bar at that same time
    #     self.df.loc[pd.to_datetime(line.pop("date"))] = line

    def tickPrice(
        self, reqId: TickerId, tickType: TickType, price: float, attrib: TickAttrib
    ):
        """Market data tick price callback. Handles all price related ticks."""

        self.logAnswer(current_fn_name(), vars())
        if tickType == 2:
            self.insert_to_queue(price)

    def nextValidId(self, orderId: int):
        self.logAnswer(current_fn_name(), vars())
        self.nextValidOrderId = orderId

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: Decimal,
        remaining: Decimal,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):
        self.logAnswer(current_fn_name(), vars())
        if status == "Filled":
            self.insert_to_queue(
                (
                    status,
                    filled,
                    remaining,
                    avgFillPrice,
                    permId,
                    parentId,
                    lastFillPrice,
                    clientId,
                    whyHeld,
                    mktCapPrice,
                )
            )
