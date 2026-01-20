import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def get_fresh_cookies(target_url, proxy_config):
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
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
        await page.goto(target_url, wait_until="networkidle")

        await asyncio.sleep(5)

        cookies_list = await context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}

        await browser.close()
        return cookies_dict


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
