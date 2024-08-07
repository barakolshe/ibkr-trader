import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum
from queue import Queue
from typing import Any, Optional

import arrow
from ibapi.client import EClient
from ibapi.common import TickAttrib, TickerId
from ibapi.contract import Contract
from ibapi.order import Order as IBOrder
from ibapi.ticktype import TickType
from ibapi.utils import current_fn_name
from ibapi.wrapper import EWrapper
from pydantic import BaseModel, ConfigDict

from consts.time_consts import AWARE_DATETIME_FORMATTING, DATETIME_FORMATTING
from consts.trading_consts import CHOSEN_STOCKS_AMOUNT
from logger.logger import logger


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
    quantity: int


class IBapi(EWrapper, EClient):  # type: ignore
    queues_mappings: dict[int, Queue[Any]]
    orders_mappings: dict[int, Order]

    order_counter: int = 0

    def __init__(self, nextValidOrderId: int = 1) -> None:
        EClient.__init__(self, self)
        self.queues_mappings: dict[int, Queue[Any]] = {}
        self.orders_mappings: dict[int, Order] = {}
        self.nextValidOrderId = nextValidOrderId

    def insert_to_queue(self, data: Any, queue: Queue[Any]) -> None:
        queue.put(data)

    def req_contract_details(self, contract: Contract) -> Queue[Any]:
        queue = Queue[Any]()
        req_id = self.nextValidOrderId
        self.nextValidOrderId += 1
        self.queues_mappings[req_id] = queue
        self.reqContractDetails(req_id, contract)

        return queue

    def contractDetails(self, reqId: int, contractDetails: Any) -> None:
        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        self.insert_to_queue(contractDetails, queue)

    def contractDetailsEnd(self, reqId: int) -> None:
        self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        self.insert_to_queue(None, queue)

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

    def req_live_data(
        self,
        contract: Contract,
        whatToShow: str,
        useRTH: int,
        realTimeBarOptions: Any,
    ) -> Queue[Any]:
        queue = Queue[Any]()
        req_id = self.nextValidOrderId
        self.nextValidOrderId += 1
        self.queues_mappings[req_id] = queue
        self.reqRealTimeBars(
            req_id, contract, 1, whatToShow, useRTH, realTimeBarOptions
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

        if reqId in self.queues_mappings and reqId not in self.orders_mappings:
            queue = self.queues_mappings[reqId]
            queue.put(None)

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

    def realtimeBar(
        self,
        reqId: TickerId,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: Decimal,
        wap: Decimal,
        count: int,
    ) -> None:
        # self.logAnswer(current_fn_name(), vars())
        queue = self.queues_mappings[reqId]
        bar_dict = {
            "date": arrow.get(time, tzinfo="US/Eastern").datetime,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "wap": wap,
            "count": count,
        }
        self.insert_to_queue(bar_dict, queue)

    def place_bracket_order(
        self,
        action: OrderType,
        quantity: int,
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
        totalQuantity: int,
        lmtPrice: float,
        auxPrice: Optional[float] = None,
        parentId: Optional[int] = None,
        orderId: Optional[int] = None,
        goodTillDate: Optional[datetime] = None,
        transmit: bool = True,
    ) -> Order:
        self.logAnswer(current_fn_name(), vars())

        self.order_counter += 1

        if self.order_counter > 4 * CHOSEN_STOCKS_AMOUNT * 2:
            raise ValueError("Too many orders")

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
            order.goodTillDate = (
                f"{arrow.get(goodTillDate).format(DATETIME_FORMATTING)} US/Eastern"
            )
            order.tif = "GTD"
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

        self.orders_mappings[order.orderId] = return_order

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
        order = self.orders_mappings[orderId]
        match (status):
            case "Filled":
                new_order = Order(
                    id=orderId,
                    queue=queue,
                    status=OrderStatus.COMPLETED,
                    order_type=order.order_type,
                    price=avgFillPrice,
                    quantity=int(filled),
                )
                queue.put(new_order)
            case "Cancelled":
                new_order = Order(
                    id=orderId,
                    queue=queue,
                    status=OrderStatus.CANCELLED,
                    order_type=order.order_type,
                    price=order.price,
                    quantity=int(filled),
                )
                queue.put(new_order)
            case "Submitted":
                new_order = Order(
                    id=orderId,
                    queue=queue,
                    status=OrderStatus.PARTIAL,
                    order_type=order.order_type,
                    price=order.price,
                    quantity=order.quantity,
                )
                queue.put(new_order)
