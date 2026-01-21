import asyncio
import logging
import httpx
import scraping
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

print(f"scraping module: {scraping.__file__}")
print(f"httpx version: {httpx.__version__}")

urls = pd.read_csv("../data/goofish_urls.csv")["URL"].tolist()[:10000]

results = asyncio.run(scraping.batch_processing(urls, concurrency=5, retries=1, use_proxy=True))

output_df = pd.DataFrame(results)
output_df.to_csv("../data/goofish_output.csv", index=False)

print(results)
