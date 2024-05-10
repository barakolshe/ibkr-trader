from decimal import Decimal
from queue import Queue
from typing import Any

from arrow import get
from consts.algorithem_consts import PRECISION
from consts.trading_consts import MAX_STOP_LOSS, MIN_TARGET_PROFIT, PERSUMED_TICK_SIZE
from ib.app import IBapi  # type: ignore
from ibapi.contract import Contract

from ib.wrapper import get_account_usd, get_contract, get_current_stock_price
from models.trading import GroupRatio, Stock
from utils.math_utils import D
from logger.logger import logger


def trade(
    app: IBapi, response_queue: Queue[Any], stock: Stock, group_ratio: GroupRatio
) -> None:
    contract: Contract = get_contract(stock.symbol, "SMART")
    action = "BUY" if group_ratio.target_profit > 0 else "SELL"
    account_usd = get_account_usd(app, response_queue)
    stock_price = get_current_stock_price(app, stock.symbol, "SMART", response_queue)
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
        stock_price + (group_ratio.stop_loss * stock_price), precision=Decimal("0.00")
    )
    if (
        abs((target_profit / stock_price) - 1) >= MIN_TARGET_PROFIT
        and abs((stop_loss / stock_price) - 1) <= MAX_STOP_LOSS
    ):
        app.placeBracketOrder(
            app.nextValidOrderId,
            action,
            quantity,
            price_limit,
            target_profit,
            stop_loss,
            contract,
        )
        response = response_queue.get()
        logger.info(response)

    print(f"Trading stock: {stock.symbol} with group ratio: {group_ratio.get_json()}")
