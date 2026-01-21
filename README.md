# Goofish Scraper

Scraper asincronico para extraer datos de productos de Goofish a partir de URLs y exponer un endpoint HTTP.

## Requisitos

- Python 3.11+
- Dependencias en `requirements.txt`
- Playwright instalado y navegadores descargados (si vas a obtener cookies con navegador)

## Configuracion

Variables de entorno opcionales para proxy (solo si `--use-proxy`):

- `PROXY_SERVER`
- `PROXY_USER`
- `PROXY_PASS`

Crea un archivo `.env` en la raiz si queres cargar estas variables automaticamente.

## Uso rapido

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Scraping a CSV desde un listado de URLs:

```bash
python utils/scrape_csv.py \
  --input data/goofish_urls.csv \
  --output data/goofish_products.csv \
  --workers 5 \
  --retries 1 \
  --timeout 45
```

Ejecutar API:

```bash
python main.py
```

Luego abrir `http://localhost:8080/docs`.

## Estrategia de scraping (50.000 productos)

La obtencion de productos se basa en un flujo híbrido: navegador para cookies + API interna para datos.

1) **Cookies con Playwright**
   - Se abre un navegador Chromium en modo stealth y se visita una URL valida.
   - Se recolectan cookies criticas (`_m_h5_tk`, `cookie2`) usadas por el endpoint interno.
   - Estas cookies se cachean con `CookieManager` y se refrescan automaticamente ante errores de token.

2) **Llamada directa al endpoint interno (mtop)**
   - Para cada URL se extrae `itemId` y se arma el payload esperado por el endpoint.
   - Se genera la firma `sign` con MD5 usando el token de cookies, timestamp y payload.
   - Se hace un POST a `h5api.m.goofish.com` para obtener el JSON de detalle.

3) **Concurrencia controlada y escalado**
   - Se encola cada URL y se reparte entre `workers` para balancear carga.
   - Cada worker usa su propio `CookieManager` con lock interno para evitar colisiones.
   - Se mantiene un cache compartido de URLs visitadas para evitar requests duplicados.
   - Se limitan reintentos a errores de token y se registra cada resultado en CSV.

4) **Rendimiento y estabilidad**
   - Se reutilizan cookies entre muchas URLs hasta que el token expira.
   - Se usan timeouts a nivel request para evitar bloqueos prolongados.
   - El scraping es idempotente y se registra el estado por URL (OK/ERROR).

## Estructura del proyecto

- `utils/scraping.py`: obtencion de cookies, firma y scraping del endpoint.
- `utils/CookieManager.py`: cache y refresh de cookies.
- `utils/scrape_csv.py`: orquestacion del scraping masivo a CSV.
- `main.py`: API FastAPI con endpoint de scraping.
- `data/`: CSVs de entrada/salida de ejemplo.

## Notas

- Para scraping masivo, ajustar `--workers` y `--timeout` segun los recursos.
- Si el endpoint devuelve errores de token, se refrescan cookies y se reintenta.
