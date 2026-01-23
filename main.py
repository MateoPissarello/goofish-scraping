"""API HTTP para exponer el scraping de un PDP de Goofish.

Esta API se usa principalmente para pruebas locales del scraping por URL.
"""

from fastapi.responses import RedirectResponse
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Query
from worker.utils.CookieManager import CookieManager
from worker.scraping.scraping_repository import scrape_one, get_fresh_cookies


# =================================================================
# FASTAPI CONFIGURATION
# =================================================================
YOUR_NAME = "Mateo Pissarello"  # TODO: actualiza con tu nombre si corresponde.


def custom_openapi():
    """Personaliza el esquema OpenAPI y elimina respuestas de validación.

    Returns:
        dict: Esquema OpenAPI modificado.
    """
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=f"Goofish Scraping API - Developed by {YOUR_NAME}",
        version="1.0.0",
        description=(
            "Prueba técnica para Backend Engineer en Iceberg Data. "
            "Esta API expone el scraping de Goofish y devuelve datos de producto."
        ),
        routes=app.routes,
    )

    if "HTTPValidationError" in openapi_schema["components"]["schemas"]:
        del openapi_schema["components"]["schemas"]["HTTPValidationError"]
    if "ValidationError" in openapi_schema["components"]["schemas"]:
        del openapi_schema["components"]["schemas"]["ValidationError"]

    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.pop("servers", None)
            if "responses" in method:
                if "422" in method["responses"]:
                    del method["responses"]["422"]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI()
app.openapi = custom_openapi


# =================================================================
# API ENDPOINTS
# =================================================================
# Redirect to the documentation
@app.get("/", include_in_schema=False, response_class=RedirectResponse, tags=["Root"])
async def redirect_to_docs():
    """Redirige al usuario hacia la documentación interactiva.

    Returns:
        str: Ruta de redirección a la documentación.
    """
    return "/docs"


@app.get("/scrapePDP", tags=["Scraping"])
async def scrape_pdp_endpoint(url: str = Query(..., description="The URL of the Goofish product to scrape")):
    """Expone el scraper como endpoint HTTP.

    Args:
        url (str): URL del producto a hacer scraping.

    Returns:
        dict: Datos normalizados del producto o un diccionario de error.
    """
    try:
        cookie_mgr = CookieManager(get_fresh_cookies, use_proxy=False)
        data = await scrape_one(url, cookie_mgr=cookie_mgr, retries=2, timeout_s=10.0)
    except Exception as e:
        return {"URL": url, "ERROR": str(e)}
    return data


# =================================================================
# TESTING
# =================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
