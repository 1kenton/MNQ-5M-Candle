import httpx
import os
import time

SCHEMA_VERSION = "1"


class SchemaError(Exception):
    pass


async def fetch(asset: str = "BTC/USDT") -> dict:
    glassnode_key = os.environ.get("GLASSNODE_API_KEY", "")
    if glassnode_key:
        # Premium: Glassnode active addresses
        url = "https://api.glassnode.com/v1/metrics/addresses/active_count"
        params = {"a": "BTC", "api_key": glassnode_key, "i": "24h", "f": "JSON"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        value = float(data[-1]["v"]) if data else 0.0
    else:
        # Free fallback: CoinGecko community data
        ticker = asset.split("/")[0].lower()
        url = f"https://api.coingecko.com/api/v3/coins/{ticker}"
        params = {"localization": "false", "tickers": "false", "market_data": "false",
                  "community_data": "true", "developer_data": "false"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        cd = data.get("community_data", {})
        value = float(cd.get("twitter_followers", 0))

    return {
        "schema_version": SCHEMA_VERSION,
        "active_addresses_proxy": value,
        "source": "glassnode" if glassnode_key else "coingecko_community",
        "ts": int(time.time()),
    }
