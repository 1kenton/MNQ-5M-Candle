import httpx
import os
import time

SCHEMA_VERSION = "1"


class SchemaError(Exception):
    pass


async def fetch(asset: str = "BTC/USDT") -> dict:
    news_key = os.environ.get("NEWS_API_KEY", "")
    keyword = asset.split("/")[0]  # BTC

    if news_key:
        url = "https://newsapi.org/v2/everything"
        params = {"q": keyword, "language": "en", "pageSize": 5,
                  "sortBy": "publishedAt", "apiKey": news_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        articles = [a["title"] for a in data.get("articles", [])]
        sentiment_proxy = len(articles)
    else:
        # Free fallback: CryptoCompare headlines (no key needed)
        url = "https://min-api.cryptocompare.com/data/v2/news/"
        params = {"categories": keyword, "lang": "EN"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        articles = [a["title"] for a in data.get("Data", [])[:5]]
        sentiment_proxy = len(articles)

    return {
        "schema_version": SCHEMA_VERSION,
        "recent_headlines": articles,
        "headline_count": sentiment_proxy,
        "source": "newsapi" if news_key else "cryptocompare",
        "ts": int(time.time()),
    }
