import os
import boto3
from hashlib import md5
import time

REGION_NAME = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
MAX_SQS_RETRIES = int(os.getenv("MAX_SQS_RETRIES", "3"))
GOOFISH_URLS_TABLE = os.getenv("GOOFISH_URLS_TABLE")
GOOFISH_SCRAPED_URLS_TABLE = os.getenv("GOOFISH_SCRAPED_URLS_TABLE")
GOOFISH_PARSED_URLS_TABLE = os.getenv("GOOFISH_PARSED_URLS_TABLE")
PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USER = os.getenv("PROXY_USER")
PROXY_PASS = os.getenv("PROXY_PASS")

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)

scraped_table = dynamodb.Table(GOOFISH_SCRAPED_URLS_TABLE)
parsed_table = dynamodb.Table(GOOFISH_PARSED_URLS_TABLE)


def url_hash(url: str) -> str:
    return md5(url.encode("utf-8")).hexdigest()


def get_job_status(url_hash: str):
    resp = scraped_table.get_item(Key={"url_hash": url_hash(url_hash)})
    return resp.get("Item")


def mark_job_as_scraped(url: str, status: str, error: str | None = None):
    item = {
        "url_hash": url_hash(url),
        "url": url,
        "status": status,
        "updated_at": int(time.time()),
        "error": error,
    }
    if error:
        item["error"] = error
    scraped_table.put_item(Item=item)


def save_data(item):
    parsed_table.put_item(Item=item)

def process_url