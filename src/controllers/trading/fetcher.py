import os
from typing import Any
import arrow
from pymongo import MongoClient

from models.evaluation import Evaluation


def transform_exchange(exchange: str) -> str:
    if exchange == "NASDAQ":
        return "ISLAND"

    return exchange


def get_actions(exchanges: list[str], all: bool) -> list[Evaluation]:
    username = os.environ.get("MONGODB_USERNAME")
    password = os.environ.get("MONGODB_PASSWORD")
    cluster_name = os.environ.get("MONGODB_CLUSTER_NAME")
    client: MongoClient[Any] = MongoClient[Any](
        f"mongodb://{username}:{password}@{cluster_name}/?retryWrites=true&w=majority&appName=best-friend"
    )
    db = client["trading"]
    collection = db["actions"]

    # Query for the specified exchanges and did_trade = False
    filters: dict[str, Any] = {"exchange": {"$in": exchanges}}
    if not all:
        filters["did_trade"] = False

    documents = collection.find(
        filters,
        {"_id": 1, "ticker": 1, "exchange": 1, "date": 1, "url": 1},
    )

    documents_list = list(documents)

    if not all and len(documents_list) > 0:  # Ensure there are documents to update
        collection.update_many(
            {"_id": {"$in": [doc["_id"] for doc in documents_list]}},
            {"$set": {"did_trade": True}},
        )

    return [
        Evaluation(
            ticker=doc["ticker"],
            exchange=transform_exchange(doc["exchange"]),
            timestamp=arrow.get(doc["date"]).to("US/Eastern").datetime,
            url=doc["url"],
        )
        for doc in documents_list
    ]
