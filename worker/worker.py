"""Worker ECS: consume URLs desde SQS, scrapea y persiste en DynamoDB.

Flujo:
1) Recibe mensajes de SQS con URLs.
2) Ejecuta scraping del PDP.
3) Guarda estado e ítems en DynamoDB.
"""

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
# Configuración
# -------------------------
REGION_NAME = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
GOOFISH_SCRAPED_URLS_TABLE = os.getenv("GOOFISH_SCRAPED_URLS_TABLE")
GOOFISH_PARSED_URLS_TABLE = os.getenv("GOOFISH_PARSED_URLS_TABLE")

IDLE_LIMIT = 60  # segundos sin mensajes antes de apagar
MAX_CONCURRENCY = 3  # URLs en paralelo por task ECS
MAX_BATCH_SIZE = 10  # mensajes por poll SQS

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
    """Marca el evento de apagado para salir del loop principal limpiamente.

    Returns:
        None
    """
    logging.info("SIGTERM/SIGINT recibido. Iniciando shutdown limpio...")
    shutdown_event.set()


# -------------------------
# Helpers
# -------------------------
def url_hash(url: str) -> str:
    """Genera un hash estable para usar como PK en DynamoDB.

    Args:
        url (str): URL completa del producto.

    Returns:
        str: Hash MD5 en hexadecimal.
    """
    return md5(url.encode("utf-8")).hexdigest()


def get_job_status(url_hash_value: str):
    """Obtiene el estado de una URL previamente procesada.

    Args:
        url_hash_value (str): Hash de la URL.

    Returns:
        dict | None: Item de DynamoDB si existe, en caso contrario None.
    """
    resp = scraped_table.get_item(Key={"url_hash": url_hash_value})
    return resp.get("Item")


def mark_job(url: str, status: str, error: str | None = None):
    """Crea o actualiza el estado de scraping de una URL.

    Args:
        url (str): URL del producto.
        status (str): Estado de scraping (IN_PROGRESS, SUCCESS, FAILED).
        error (str | None): Mensaje de error si aplica.
    """
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
    """Guarda el ítem parseado en la tabla de resultados.

    Args:
        item (dict): Item normalizado para persistir.
    """
    parsed_table.put_item(Item=item)


# -------------------------
# Message handler
# -------------------------
async def handle_message(msg, scraper, semaphore):
    """Procesa un mensaje SQS con control de concurrencia.

    Args:
        msg (dict): Mensaje recibido desde SQS.
        scraper (PdpScrapper): Instancia de scraper con cookies compartidas.
        semaphore (asyncio.Semaphore): Semáforo para limitar concurrencia.

    Returns:
        None
    """
    async with semaphore:
        receipt = msg["ReceiptHandle"]
        body = json.loads(msg["Body"])
        product_url = body["url"]

        logging.info("Procesando URL: %s", product_url)

        h = url_hash(product_url)
        status = get_job_status(h)

        # Idempotencia
        if status and status.get("status") == "SUCCESS":
            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=receipt,
            )
            logging.info("URL ya procesada: %s", product_url)
            return

        try:
            mark_job(product_url, "IN_PROGRESS")
            start = time.monotonic()

            data = await scraper.scrape(product_url)

            duration = time.monotonic() - start
            logging.info("Scrape URL %s tomó %.2f segundos", product_url, duration)

            if "ERROR" in data:
                raise Exception(data["ERROR"])

            save_data(data)
            mark_job(product_url, "SUCCESS")

            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=receipt,
            )

            logging.info("URL procesada OK: %s", product_url)

        except Exception as e:
            logging.exception("Error procesando URL %s", product_url)
            mark_job(product_url, "FAILED", str(e))


# -------------------------
# Main loop
# -------------------------
async def main():
    """Loop principal: long polling en SQS y procesamiento concurrente.

    Returns:
        None
    """
    idle_time = 0
    loop = asyncio.get_running_loop()

    loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
    loop.add_signal_handler(signal.SIGINT, handle_shutdown)

    logging.info("Worker iniciado, esperando mensajes...")

    while not shutdown_event.is_set():
        resp = await asyncio.to_thread(
            sqs.receive_message,
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=MAX_BATCH_SIZE,
            WaitTimeSeconds=20,
        )

        messages = resp.get("Messages", [])

        if not messages:
            await asyncio.sleep(5)
            idle_time += 5

            if idle_time >= IDLE_LIMIT:
                logging.info("Límite de inactividad alcanzado, apagando worker.")
                break

            continue

        idle_time = 0

        scraper = PdpScrapper()
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        tasks = [handle_message(msg, scraper, semaphore) for msg in messages]

        await asyncio.gather(*tasks)

    logging.info("Worker apagado limpiamente.")


if __name__ == "__main__":
    asyncio.run(main())
