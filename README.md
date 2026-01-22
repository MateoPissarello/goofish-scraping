# Goofish Scraper (Iceberg Data)

Pipeline de scraping asíncrona para extraer datos de productos de Goofish a partir de URLs y procesarlos en AWS con S3 → Lambda → SQS → ECS Fargate. Incluye un endpoint HTTP opcional para pruebas locales.

## Arquitectura

1) **Carga de URLs**: se sube un CSV a S3 (columna `URL`).
2) **Lambda (S3→SQS)**: al detectar el CSV, envía las URLs a SQS en batches de 10.
3) **Workers (ECS Fargate)**: consumen mensajes de SQS, hacen scraping del PDP y guardan resultados en DynamoDB.
4) **DynamoDB**:
   - `*-scraped-urls`: idempotencia y status por URL.
   - `*-parsed-items`: ítems parseados.
5) **Autoscaling**: escala por cantidad de mensajes visibles en SQS.

## Componentes

- `worker/worker.py`: loop principal del worker (SQS → scrape → DynamoDB).
- `worker/scraping/scraping_repository.py`: lógica de cookies, firma y request al endpoint interno.
- `worker/scraping/PdpScraper.py`: wrapper de scraping por URL.
- `lambda/s3_to_sqs.py`: Lambda que lee CSV desde S3 y publica en SQS.
- `infra/`: Terraform para S3, SQS, DynamoDB, ECS, IAM, CloudWatch y Secrets Manager.
- `main.py`: API FastAPI para probar scraping por URL.

## Requisitos

- Python 3.11+
- Playwright + Chromium
- Cuenta de AWS con permisos para crear los recursos
- Terraform >= 1.5
- Docker (para construir la imagen del worker)

## Configuración

### Variables de entorno (worker)

- `AWS_REGION`
- `SQS_QUEUE_URL`
- `GOOFISH_SCRAPED_URLS_TABLE`
- `GOOFISH_PARSED_URLS_TABLE`
- `PROXY_SERVER`, `PROXY_USER`, `PROXY_PASS` (requeridas si `use_proxy=True`)


### Variables de entorno (API local)

Para la API de `main.py` no se usa proxy por defecto (`use_proxy=False`).

Opcionalmente puedes definir un `.env` con credenciales de proxy si quieres probar con proxy.

## Uso local

Instalar dependencias:

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
```

Levantar API local:

```bash
python main.py
```

Abrir en el navegador:

```
http://localhost:8080/docs
```

Endpoint principal:

```
GET /scrapePDP?url=https://www.goofish.com/item?id=XXXX
```

## Deploy en AWS (Terraform)

Desde `infra/`:

```bash
terraform init
terraform apply \
  -var 'ecr_image_url=123456789012.dkr.ecr.us-east-1.amazonaws.com/iceberg-scraper-worker:latest' \
  -var 'proxy_server=host:port' \
  -var 'proxy_user=usuario' \
  -var 'proxy_pass=pass'
```

Outputs relevantes:

- `datasets_bucket_name` (sube CSVs aquí)
- `sqs_queue_url`
- `ecs_service_name`
- `log_group_name`

## Build & push del worker

```bash
docker build -t iceberg-scraper-worker .
# tag y push a ECR según tu cuenta
```

## Ingesta de URLs

1) Sube un CSV a S3 con columna `URL`.
2) La Lambda enviará las URLs a SQS.
3) Los workers procesan y guardan resultados en DynamoDB.

Ejemplo de CSV:

```csv
URL
https://www.goofish.com/item?id=894551126004
```

## Notas

- La idempotencia se maneja en DynamoDB usando `url_hash`.
- Si el endpoint devuelve errores de token, se refrescan cookies y se reintenta.
- El timeout de SQS se controla con `sqs_visibility_timeout_seconds` en Terraform.
- El autoscaling se basa en la métrica `ApproximateNumberOfMessagesVisible` de SQS.
