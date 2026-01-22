import os
import json
import time
import asyncio
import boto3
import logging
import signal
from hashlib import md5

from worker.scraping.PdpScraper import PdpScrapper

# -------------------------
# Config
# -------------------------
REGION_NAME = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
GOOFISH_SCRAPED_URLS_TABLE = os.getenv("GOOFISH_SCRAPED_URLS_TABLE")
GOOFISH_PARSED_URLS_TABLE = os.getenv("GOOFISH_PARSED_URLS_TABLE")

logging.basicConfig(level=logging.INFO)

sqs = boto3.client("sqs", region_name=REGION_NAME)
dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)

scraped_table = dynamodb.Table(GOOFISH_SCRAPED_URLS_TABLE)
parsed_table = dynamodb.Table(GOOFISH_PARSED_URLS_TABLE)

# -------------------------
# Shutdown handling
# -------------------------
shutdown_event = asyncio.Event()


def handle_shutdown():
    logging.info("SIGTERM/SIGINT recibido. Iniciando shutdown limpio...")
    shutdown_event.set()


# -------------------------
# Helpers
# -------------------------
def url_hash(url: str) -> str:
    return md5(url.encode("utf-8")).hexdigest()


def get_job_status(url_hash_value: str):
    resp = scraped_table.get_item(Key={"url_hash": url_hash_value})
    return resp.get("Item")


def mark_job(url: str, status: str, error: str | None = None):
    item = {
        "url_hash": url_hash(url),
        "url": url,
        "status": status,
        "updated_at": int(time.time()),
    }
    if error:
        item["error"] = error

    scraped_table.put_item(Item=item)


def save_data(item: dict):
    parsed_table.put_item(Item=item)


async def process_url(url: str):
    scraper = PdpScrapper()
    return await scraper.scrape(url)


# -------------------------
# Main loop
# -------------------------
async def main():
    loop = asyncio.get_running_loop()

    # Registrar handlers de señal
    loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
    loop.add_signal_handler(signal.SIGINT, handle_shutdown)

    logging.info("Worker iniciado, esperando mensajes...")

    while not shutdown_event.is_set():
        resp = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
        )

        messages = resp.get("Messages", [])
        if not messages:
            if shutdown_event.is_set():
                break
            continue

        msg = messages[0]
        receipt = msg["ReceiptHandle"]

        body = json.loads(msg["Body"])
        product_url = body["url"]
        logging.info("Procesando URL: %s", product_url)

        h = url_hash(product_url)
        status = get_job_status(h)

        if status and status.get("status") == "SUCCESS":
            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=receipt,
            )
            logging.info("URL ya procesada exitosamente: %s", product_url)
            continue

        try:
            mark_job(product_url, "IN_PROGRESS")

            data = await process_url(product_url)

            logging.info("Datos scrapeados: %s", data)
            save_data(data)

            mark_job(product_url, "SUCCESS")
            logging.info("URL procesada exitosamente: %s", product_url)

            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=receipt,
            )

        except Exception as e:
            logging.exception("Error procesando URL %s", product_url)
            mark_job(product_url, "FAILED", str(e))
            # ❌ No borrar mensaje → SQS retry / DLQ

    logging.info("Worker apagado limpiamente.")


if __name__ == "__main__":
    asyncio.run(main())
