import json
from typing import Any
import boto3


def get_file_from_bucket(file_name: str) -> str:
    s3 = boto3.resource(
        "s3",
        region_name="il-central-1",
    )
    obj = s3.Object("barak-trading-bucket", file_name)

    data: str = obj.get()["Body"].read()

    return data


def get_stocks_json_from_bucket() -> Any:
    return json.loads(get_file_from_bucket("stocks.json"))
