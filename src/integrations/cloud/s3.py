import time
import ujson
from typing import Any
import boto3

from consts.networking_consts import S3_BUCKET_NAME


def get_file_from_bucket(file_name: str) -> str:
    s3 = boto3.resource(
        "s3",
        region_name="il-central-1",
    )
    obj = s3.Object(S3_BUCKET_NAME, file_name)

    data: str = obj.get()["Body"].read()

    return data


def get_stocks_json_from_bucket() -> Any:
    return ujson.loads(get_file_from_bucket("stocks.json"))


def wait_for_kill_all_command() -> None:
    s3_client = boto3.client("s3")
    while True:
        try:
            s3_client.get_object(Bucket=S3_BUCKET_NAME, Key="exit2.json")
            s3_client.delete_objects(
                Bucket=S3_BUCKET_NAME,
                Delete={
                    "Objects": [
                        {
                            "Key": "exit2.json",
                        },
                    ],
                },
            )
            return
        except:
            time.sleep(10)
