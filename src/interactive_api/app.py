from datetime import datetime
from decimal import Decimal
from enum import Enum
import logging
from queue import Queue
from typing import Any, Optional
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.utils import current_fn_name
import arrow
from ibapi.order import Order as IBOrder
from ibapi.contract import Contract
from ibapi.common import TickAttrib, TickerId
from ibapi.ticktype import TickType
from pydantic import BaseModel, ConfigDict

from consts.time_consts import AWARE_DATETIME_FORMATTING
from logger.logger import logger
from utils.math_utils import D


class OrderType(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"
    SENT = "SENT"


class Order(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    queue: Queue[Any]
    status: OrderStatus
    order_type: OrderType
    price: float
    quantity: float


class IBapi(EWrapper, EClient):  # type: ignore
    queues_mappings: dict[int, Queue[Any]]

    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.queues_mappings: dict[int, Queue[Any]] = {}
        self.nextValidOrderId = 1

    def insert_to_queue(self, data: Any, queue: Queue[Any]) -> None:
        queue.put(data)

    def req_historical_data(
        self,
        contract: Contract,
        endDateTime: str,
        durationStr: str,
        barSizeSetting: str,
        whatToShow: str,
        useRTH: int,
        formatDate: int,
        keepUpToDate: bool,
        chartOptions: Any,
    ) -> Queue[Any]:
        queue = Queue[Any]()
        req_id = self.nextValidOrderId
        self.nextValidOrderId += 1
        self.queues_mappings[req_id] = queue
        self.reqHistoricalData(
            req_id,
            contract,
            endDateTime,
            durationStr,
            barSizeSetting,
            whatToShow,
            useRTH,
            formatDate,
            keepUpToDate,
            chartOptions,
        )

        return queue

    def req_account_summary(self, groupName: str, tags: str) -> Queue[Any]:
        queue = Queue[Any]()
        req_id = self.nextValidOrderId
        self.nextValidOrderId += 1
        self.queues_mappings[req_id] = queue
        self.reqAccountSummary(req_id, groupName, tags)

        return queue

    def logAnswer(self, fnName: str, fnParams: Any) -> None:
        if logger.isEnabledFor(logging.INFO):
            if "self" in fnParams:
                prms = dict(fnParams)
                del prms["self"]
            else:
                prms = fnParams
            logger.debug("ANSWER function: %s, parameters: %s", fnName, prms)

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ) -> None:
        """This event is called when there is an error with the
        communication or when TWS wants to send a message to the client."""
        if reqId == -1:
            return
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

        if reqId in self.queues_mappings:
            queue = self.queues_mappings[reqId]
            self.insert_to_queue(None, queue)
            self.queues_mappings.pop(reqId)

    def historicalData(self, reqId: int, bar: Any) -> None:
        # self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        bar_dict = vars(bar)
        bar_dict["date"] = arrow.get(
            bar_dict["date"], AWARE_DATETIME_FORMATTING
        ).datetime
        self.insert_to_queue(bar_dict, queue)

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        self.insert_to_queue(None, queue)
        self.queues_mappings.pop(reqId)

    def place_bracket_order(
        self,
        action: OrderType,
        quantity: float,
        price_limit: float,
        take_profit_limit_price: float,
        stop_loss_price: float,
        stop_loss_limit_price: float,
        parent_valid: datetime,
        children_valid: datetime,
        contract: Contract,
    ) -> tuple[Order, Order, Order]:
        self.logAnswer(current_fn_name(), vars())
        parent_order = self.place_order(
            contract=contract,
            action=action,
            orderType="LMT",
            totalQuantity=quantity,
            lmtPrice=price_limit,
            transmit=False,
            goodTillDate=parent_valid,
        )

        limit_price_order = self.place_order(
            contract=contract,
            action=OrderType.SELL if action == OrderType.BUY else OrderType.BUY,
            orderType="LMT",
            totalQuantity=quantity,
            lmtPrice=take_profit_limit_price,
            transmit=False,
            parentId=parent_order.id,
            goodTillDate=children_valid,
        )

        stop_loss_order = self.place_order(
            contract=contract,
            action=OrderType.SELL if action == OrderType.BUY else OrderType.BUY,
            orderType="STP LMT",
            totalQuantity=quantity,
            auxPrice=stop_loss_price,
            lmtPrice=stop_loss_limit_price,
            transmit=True,
            parentId=parent_order.id,
            goodTillDate=children_valid,
        )

        return parent_order, limit_price_order, stop_loss_order

    def place_order(
        self,
        contract: Contract,
        action: OrderType,
        orderType: str,
        totalQuantity: float,
        lmtPrice: float,
        auxPrice: Optional[float] = None,
        parentId: Optional[int] = None,
        orderId: Optional[int] = None,
        goodTillDate: Optional[datetime] = None,
        transmit: bool = True,
    ) -> Order:
        self.logAnswer(current_fn_name(), vars())
        order = IBOrder()
        if orderId:
            order.orderId = orderId
        else:
            order.orderId = self.nextValidOrderId
            self.nextValidOrderId += 1
        order.action = "BUY" if action == OrderType.BUY else "SELL"
        order.orderType = orderType
        order.totalQuantity = totalQuantity
        if auxPrice:
            order.auxPrice = auxPrice
        if lmtPrice:
            order.lmtPrice = lmtPrice
        if parentId:
            order.parentId = parentId
        if goodTillDate:
            order.goodTillDate = goodTillDate.strftime(AWARE_DATETIME_FORMATTING)
        order.transmit = transmit

        queue = Queue[Any]()
        self.queues_mappings[order.orderId] = queue
        return_order = Order(
            id=order.orderId,
            queue=queue,
            status=OrderStatus.SENT,
            order_type=action,
            price=lmtPrice,
            quantity=totalQuantity,
        )

        self.placeOrder(order.orderId, contract, order)

        return return_order

    def accountSummary(
        self, reqId: int, account: str, tag: str, value: str, currency: str
    ) -> None:
        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        self.insert_to_queue((tag, value), queue)

    def accountSummaryEnd(self, reqId: int) -> None:
        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        self.insert_to_queue(None, queue)
        self.queues_mappings.pop(reqId)

    # def historicalDataUpdate(self, reqId, bar):
    #     line = vars(bar)
    #     # pop date and make it the index, add rest to df
    #     # will overwrite last bar at that same time
    #     self.df.loc[pd.to_datetime(line.pop("date"))] = line

    def tickPrice(
        self, reqId: TickerId, tickType: TickType, price: float, attrib: TickAttrib
    ) -> None:
        """Market data tick price callback. Handles all price related ticks."""

        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        if tickType == 2:
            self.insert_to_queue(price, queue)

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
    ) -> None:
        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[orderId]
        if status == "Filled":
            self.insert_to_queue(
                {
                    "order_id": orderId,
                    "status": status,
                    "filled": filled,
                    "remaining": remaining,
                    "avgFillPrice": avgFillPrice,
                    "permId": permId,
                    "parentId": parentId,
                    "lastFillPrice": lastFillPrice,
                    "clientId": clientId,
                    "whyHeld": whyHeld,
                    "mktCapPrice": mktCapPrice,
                },
                queue,
            )
