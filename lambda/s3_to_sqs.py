"""Lambda que envía URLs desde un CSV en S3 hacia SQS."""

import json
import csv
import boto3
import os
import urllib.parse

s3 = boto3.client("s3")
sqs = boto3.client("sqs")

QUEUE_URL = os.environ["SQS_QUEUE_URL"]


def handler(event, context):
    """Handler de Lambda para eventos S3 ObjectCreated.

    Args:
        event: Evento de S3 con registros de objetos creados.
        context: Contexto Lambda (no usado).
    """
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        obj = s3.get_object(Bucket=bucket, Key=key)

        # Streaming del body
        lines = obj["Body"].iter_lines()
        reader = csv.DictReader(
            (line.decode("utf-8") for line in lines)
        )

        batch = []
        total = 0

        for row in reader:
            url = (row.get("URL") or "").strip()
            if not url:
                continue

            batch.append({
                "Id": str(len(batch)),
                "MessageBody": json.dumps({"url": url}),
            })

            # Enviar batch de 10
            if len(batch) == 10:
                sqs.send_message_batch(
                    QueueUrl=QUEUE_URL,
                    Entries=batch,
                )
                total += len(batch)
                batch = []

        # Enviar resto
        if batch:
            sqs.send_message_batch(
                QueueUrl=QUEUE_URL,
                Entries=batch,
            )
            total += len(batch)

        print(f"Sent {total} URLs to SQS from {key}")
