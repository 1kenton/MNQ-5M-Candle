import httpx
import time

SCHEMA_VERSION = "1"


class SchemaError(Exception):
    pass


async def fetch(asset: str = "BTC/USDT") -> dict:
    # Free: Binance BTC dominance proxy via global market cap from CoinGecko
    url = "https://api.coingecko.com/api/v3/global"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    gdata = data.get("data", {})
    required = {"market_cap_percentage", "total_market_cap"}
    if not required.issubset(gdata.keys()):
        raise SchemaError(f"macro adapter schema mismatch: missing {required - set(gdata.keys())}")

    btc_dom = gdata["market_cap_percentage"].get("btc", 0.0)
    total_mcap_usd = gdata["total_market_cap"].get("usd", 0.0)

    return {
        "schema_version": SCHEMA_VERSION,
        "btc_dominance_pct": float(btc_dom),
        "total_market_cap_usd": float(total_mcap_usd),
        "source": "coingecko_global",
        "ts": int(time.time()),
    }
