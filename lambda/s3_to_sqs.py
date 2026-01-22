import json
import csv
import boto3
import os
import urllib.parse

s3 = boto3.client("s3")
sqs = boto3.client("sqs")

QUEUE_URL = os.environ["SQS_QUEUE_URL"]


def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        obj = s3.get_object(Bucket=bucket, Key=key)
        lines = obj["Body"].read().decode("utf-8").splitlines()

        reader = csv.DictReader(lines)
        count = 0

        for row in reader:
            url = (row.get("URL") or "").strip()
            if not url:
                continue

            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps({"url": url}),
            )
            count += 1

        print(f"Sent {count} URLs to SQS from {key}")
