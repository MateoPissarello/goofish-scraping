from worker import ScrapeWorker

proxy = {
    "server": "gw.netnut.net:5959",
    "user": "codify-dc-any",
    "pass": "58ADAB79s03h8TJ",
}

url = "https://www.goofish.com/item?id=995598771021"

worker = ScrapeWorker(proxy)

print("Inicializando sesión (Playwright)…")
worker.init_session(url)

print("Scrapeando item…")
product = worker.scrape_item(url)

print("\nRESULTADO:")
print(product)
