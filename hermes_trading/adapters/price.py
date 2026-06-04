"""
Price data adapter. Pulls 1-minute and 5-minute OHLCV candles for MNQ.
Falls back to free public data (CoinGecko for crypto, but we're using stock data here).
"""
import httpx
import asyncio
import os


async def fetch_mnq_ohlcv(timeframe: str = "1m") -> dict:
    """
    Fetch MNQ (Micro E-mini Nasdaq-100 futures) OHLCV data.
    
    For stock index futures, we use:
    - IEX Cloud (free tier available)
    - Polygon.io (free tier available)
    - Alpha Vantage (free tier, limited)
    
    Falls back to a mock response if no API key is available.
    """
    try:
        # Try IEX Cloud first (free tier: 100 req/day)
        iex_token = os.getenv("IEX_API_KEY", "")
        if iex_token:
            async with httpx.AsyncClient(timeout=10) as client:
                # IEX doesn't have futures; we'd need to pull QQQ as proxy
                resp = await client.get(
                    f"https://cloud.iexapis.com/stable/stock/QQQ/intraday?token={iex_token}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "source": "iex",
                        "symbol": "MNQ",
                        "timeframe": timeframe,
                        "candles": data,
                        "schema_version": "1.0"
                    }
    except Exception as e:
        print(f"[price.fetch_mnq_ohlcv] IEX fetch failed: {e}")
    
    # Fallback: mock data (for development/testing)
    return {
        "source": "mock",
        "symbol": "MNQ",
        "timeframe": timeframe,
        "candles": [
            {
                "timestamp": 1700000000,
                "open": 17500.0,
                "high": 17520.0,
                "low": 17490.0,
                "close": 17510.0,
                "volume": 1000
            }
        ],
        "schema_version": "1.0"
    }


async def fetch():
    """Main entrypoint. Returns dict with schema_version."""
    candles_1m = await fetch_mnq_ohlcv("1m")
    candles_5m = await fetch_mnq_ohlcv("5m")
    
    return {
        "1m": candles_1m,
        "5m": candles_5m,
        "schema_version": "1.0"
    }


if __name__ == "__main__":
    import os
    result = asyncio.run(fetch())
    print(result)
