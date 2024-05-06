# type: ignore
import logging
from queue import Queue
from typing import Any
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.utils import current_fn_name
import pandas as pd
import arrow

from consts.time_consts import AWARE_DATETIME_FORMATTING
from logger.logger import logger


class IBapi(EWrapper, EClient):  # type: ignore
    def __init__(self, queue: Queue[Any]) -> None:
        EClient.__init__(self, self)
        self.data = []
        self.df = None
        self.queue = queue

    # Logging

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
            self.queue.put(None)
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
        logger.info(f"HistoricalData. ReqId: {reqId}, BarData: {bar}")
        bar_dict = vars(bar)
        bar_dict["date"] = arrow.get(
            bar_dict["date"], AWARE_DATETIME_FORMATTING
        ).datetime
        self.data.append(vars(bar))

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        logger.info(f"HistoricalDataEnd. ReqId: {reqId}, from: {start}, to: {end}")
        self.df = pd.DataFrame(self.data)
        self.df.set_index("date", inplace=True)
        self.queue.put(self.df)
        self.df = None
        self.data = []

    # def historicalDataUpdate(self, reqId, bar):
    #     line = vars(bar)
    #     # pop date and make it the index, add rest to df
    #     # will overwrite last bar at that same time
    #     self.df.loc[pd.to_datetime(line.pop("date"))] = line

    # def nextValidId(self, orderId: int):
    #     logger.info(f"Setting nextValidOrderId: {orderId}")
    #     self.nextValidOrderId = orderId
    #     self.start()
