import logging
import time
import boto3

from consts.networking_consts import S3_BUCKET_NAME

boto3.set_stream_logger("", logging.INFO)


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
