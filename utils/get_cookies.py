import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def get_fresh_cookies(target_url, proxy_config, timeout=60.0):
    browser = None

    async def _fetch():
        nonlocal browser
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(
                headless=False,
                proxy={
                    "server": f"http://{proxy_config['server']}",
                    "username": proxy_config["user"],
                    "password": proxy_config["pass"],
                },
            )

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )

            page = await context.new_page()

            print("Navegando a Goofish con la IP del proxy...")
            await page.goto(target_url, wait_until="networkidle", timeout=30000)

            await asyncio.sleep(5)

            cookies_list = await context.cookies()
            cookies_dict = {c["name"]: c["value"] for c in cookies_list}

            return cookies_dict

    try:
        return await asyncio.wait_for(_fetch(), timeout=timeout)
    finally:
        if browser is not None:
            await browser.close()


proxy = {
    "server": "gw.netnut.net:5959",
    "user": "codify-dc-any",
    "pass": "58ADAB79s03h8TJ",
}

url = "https://www.goofish.com/item?id=995598771021"

if __name__ == "__main__":
    cookies = asyncio.run(get_fresh_cookies(url, proxy))
    print("\n--- COPIA ESTAS COOKIES EN TU PDPHANDLER ---\n")
    print(json.dumps(cookies, indent=2))
