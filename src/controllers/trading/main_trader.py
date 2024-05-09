from queue import Queue
from typing import Any
from ib.app import IBapi  # type: ignore
from ib.wrapper import get_account_usd
from models.trading import GroupRatio, Stock


def trade(
    app: IBapi, response_queue: Queue[Any], stock: Stock, group_ratio: GroupRatio
) -> None:
    usd = get_account_usd(app, response_queue)
    action = "BUY" if group_ratio.target_profit > 0 else "SELL"
    app.placeBracketOrder(
        app.nextValidOrderId,
        action,
        quantity=4,
    )
    print(f"Trading stock: {stock.symbol} with group ratio: {group_ratio.get_json()}")
