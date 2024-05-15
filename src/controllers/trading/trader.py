from decimal import Decimal
from queue import Queue
import time
from typing import Any, Optional
from ibapi.order import Order
import arrow

from consts.algorithem_consts import PRECISION
from consts.time_consts import TIMEZONE
from consts.trading_consts import MAX_STOP_LOSS, MIN_TARGET_PROFIT, PERSUMED_TICK_SIZE
from controllers.evaluation.groups import get_group_for_score
from ib.app import IBapi  # type: ignore
from ibapi.contract import Contract
from ib.wrapper import get_account_usd, get_contract, get_current_stock_price
from models.trading import GroupRatio, Position, Stock
from persistency.data_handler import load_groups_from_file
from utils.math_utils import D
from logger.logger import logger


class Trader:
    app: IBapi
    groups: list[GroupRatio]
    trade_events_queue: Queue[Optional[Stock]]
    app_queue: Queue[Any]
    kill_queue: Queue[Any]

    open_positions: list[Position] = []

    def __init__(
        self,
        app: IBapi,
        trade_event_queue: Queue[Optional[Stock]],
        app_queue: Queue[Any],
        kill_queue: Queue[Any],
    ) -> None:
        self.app = app
        self.groups = load_groups_from_file()
        self.trade_events_queue = trade_event_queue
        self.app_queue = app_queue
        self.kill_queue = kill_queue

    def should_exit(self) -> bool:
        return not self.kill_queue.empty()

    def wait_for_open_positions(self) -> None:
        logger.info("Waiting for open positions")
        while len(self.open_positions) > 0:
            trade: Optional[dict[Any, Any]] = None
            try:
                trade = self.app_queue.get(timeout=10)
            except:
                pass
            if trade is not None and trade["status"] == "Filled":
                for open_position in self.open_positions:
                    if open_position.order_id == trade["order_id"]:
                        self.open_positions.remove(open_position)
                        break
            for open_position in self.open_positions:
                if (
                    open_position.datetime
                    >= arrow.get(open_position.datetime, TIMEZONE)
                    .shift(minute=5)
                    .datetime
                ):
                    self.close_trade(open_position)
                    self.open_positions.remove(open_position)

    def close_trade(self, position: Position) -> None:
        logger.info(f"Closing trade for stock: {position.symbol}")
        contract: Contract = get_contract(position.symbol, "SMART")
        order_id = self.app.nextValidOrderId
        current_stock_price = get_current_stock_price(
            self.app, position.symbol, "SMART", self.app_queue
        )
        order = Order()
        order.orderId = order_id
        order.action = "SELL" if position.quantity > 0 else "BUY"
        order.orderType = "LMT"
        order.totalQuantity = position.quantity
        order.lmtPrice = (
            current_stock_price + D("0.01") * current_stock_price
            if order.action == "BUY"
            else current_stock_price + D("0.01") * current_stock_price
        )
        self.app.placeOrder(self.app.nextValidOrderId, contract, order)
        response = self.app_queue.get()
        logger.info(response)

    def main_loop(self, is_test: bool = False) -> None:
        try:
            while True:
                self.wait_for_open_positions()
                if self.should_exit():
                    return
                stock: Optional[Stock] = None
                try:
                    stock = self.trade_events_queue.get(timeout=10)
                except Exception:
                    continue
                if stock is None:
                    continue

                datetime = stock.article.datetime
                if datetime < arrow.now(tz=TIMEZONE).shift(minutes=-2).datetime:
                    logger.info("Stock is too old, skipping")
                    continue
                matching_group = get_group_for_score(
                    self.groups,
                    stock.score,
                )
                self.trade(stock, matching_group)
                if is_test:
                    self.wait_for_open_positions()
                    return
        except Exception:
            logger.critical("Error in main loop", exc_info=True)
            raise

    def trade(
        self,
        stock: Stock,
        group_ratio: GroupRatio,
    ) -> None:
        logger.info(
            f"Trading stock: {stock.symbol} with group ratio: {group_ratio.get_json()}"
        )
        contract: Contract = get_contract(stock.symbol, "SMART")
        action = "BUY" if group_ratio.target_profit > 0 else "SELL"
        stock_price = get_current_stock_price(
            self.app, stock.symbol, "SMART", self.app_queue
        )
        if not (1 <= stock_price <= 30):
            return
        account_usd = get_account_usd(self.app, self.app_queue)
        quantity = int(account_usd / stock_price)
        price_limit = D(
            (
                stock_price + stock_price * D("0.01")
                if action == "BUY"
                else stock_price - stock_price * D("0.01")
            ),
            precision=Decimal("0.00"),
        )
        target_profit = D(
            stock_price + (group_ratio.target_profit * stock_price),
            precision=Decimal("0.00"),
        )
        stop_loss = D(
            stock_price + (group_ratio.stop_loss * stock_price),
            precision=Decimal("0.00"),
        )
        if (
            abs((target_profit / stock_price) - 1) >= MIN_TARGET_PROFIT
            and abs((stop_loss / stock_price) - 1) <= MAX_STOP_LOSS
        ):
            self.app.placeBracketOrder(
                self.app.nextValidOrderId,
                action,
                quantity,
                price_limit,
                target_profit,
                stop_loss,
                contract,
            )
            response = self.app_queue.get()
            logger.info(response)
            self.open_positions.append(
                Position(
                    order_id=response["order_id"],
                    symbol=stock.symbol,
                    quantity=D(quantity),
                    datetime=arrow.now(tz=TIMEZONE).datetime,
                )
            )

        print(
            f"Trading stock: {stock.symbol} with group ratio: {group_ratio.get_json()}"
        )
