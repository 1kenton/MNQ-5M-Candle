"""
Price data adapter — Yahoo Finance chart API for NQ=F (E-mini Nasdaq futures).
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; paper-trader/1.0)",
    "Accept": "application/json",
}


async def fetch_ohlcv(symbol: str = "NQ=F", interval: str = "1m", period: str = "1d") -> list:
    """
    Fetch OHLCV candles from Yahoo Finance chart API.
    Returns list of dicts sorted oldest-first.
    Each dict: {timestamp, open, high, low, close, volume}
    """
    url = _YF_CHART.format(symbol=symbol)
    params = {"interval": interval, "range": period}

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=20, headers=_HEADERS) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            result = data["chart"]["result"]
            if not result:
                return []

            r = result[0]
            timestamps = r.get("timestamp", [])
            quote = r["indicators"]["quote"][0]
            opens  = quote.get("open", [])
            highs  = quote.get("high", [])
            lows   = quote.get("low", [])
            closes = quote.get("close", [])
            vols   = quote.get("volume", [])

            candles = []
            for i, ts in enumerate(timestamps):
                o = opens[i] if i < len(opens) else None
                h = highs[i] if i < len(highs) else None
                l = lows[i] if i < len(lows) else None
                c = closes[i] if i < len(closes) else None
                v = vols[i] if i < len(vols) else 0
                if None in (o, h, l, c):
                    continue
                candles.append({
                    "timestamp": ts,
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v) if v else 0.0,
                })
            candles.sort(key=lambda c: c["timestamp"])
            return candles

        except Exception as e:
            if attempt == 2:
                logger.error(f"fetch_ohlcv({symbol},{interval}) failed after 3 tries: {e}")
                return []
            await asyncio.sleep(2 ** attempt)

    return []
