"""
One Candle Setup — NQ/MNQ Futures, 9:30 AM ET opening range breakout.

Strategy (youtu.be/sVkmZklJDHI):
  Step 1: At 9:30 AM ET, record the HIGH and LOW of the first 5-minute candle
          (completes at 9:35 AM).  That is the "opening range."
  Step 2: On the 1-minute chart, wait for a candle to CLOSE outside the range.
          The close direction determines the trade bias (long or short).
  Step 3: After the break, scan subsequent 1-minute candles for a Fair Value Gap
          (FVG) that is fully OUTSIDE the range.
          FVG definition — three consecutive 1m candles where:
            * LONG  FVG: high(c1) < low(c3)   (bullish impulse leaves a gap)
            * SHORT FVG: low(c1)  > high(c3)  (bearish impulse leaves a gap)
  Step 4: Entry  = close of the 3rd FVG candle.
          Stop   = high(c1) for LONG (lower FVG boundary);
                   low(c1)  for SHORT (upper FVG boundary).
          Target = entry +/- abs(entry - stop) x rr_ratio
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from hermes_trading.adapters.price import fetch_ohlcv

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
PAPER_MODE    = os.getenv("HERMES_TRADING_MODE", "paper") == "paper"
STATE_FILE    = Path("state/worker_state.json")
TRADES_FILE   = Path("state/trades.jsonl")
STRATEGY_FILE = Path("state/strategy.yaml")
GOAL_FILE     = Path("state/goal.yaml")

TICK_SECONDS = 60


def load_params() -> dict:
    try:
        raw = yaml.safe_load(STRATEGY_FILE.read_text()) or {}
        e = raw.get("entry", {})
        return {
            "rr_ratio":         float(e.get("rr_ratio",         2.0)),
            "sl_buffer_pct":    float(e.get("sl_buffer_pct",    0.001)),
            "fvg_min_gap_pct":  float(e.get("fvg_min_gap_pct",  0.0)),
            "trade_window_end": int(e.get("trade_window_end",   1100)),
        }
    except Exception:
        return {"rr_ratio": 2.0, "sl_buffer_pct": 0.001,
                "fvg_min_gap_pct": 0.0, "trade_window_end": 1100}


def reflection_due() -> bool:
    try:
        goal = yaml.safe_load(GOAL_FILE.read_text()) or {}
    except Exception:
        goal = {}
    every = int(goal.get("reflection_every", 5))
    if not TRADES_FILE.exists():
        return False
    closed = sum(1 for line in TRADES_FILE.read_text().splitlines() if line.strip())
    return closed > 0 and closed % every == 0


def load_state() -> dict:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"current_trade": None, "traded_today": False, "last_trade_date": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_trade(record: dict) -> None:
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRADES_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


# ── opening range + FVG helpers ────────────────────────────────────────────────

def get_opening_range(candles_5m: list, date_et: str) -> dict | None:
    """Find the 9:30 AM ET 5m candle and return its range."""
    for c in candles_5m:
        dt_et = datetime.fromtimestamp(c["timestamp"], tz=ET)
        if dt_et.strftime("%Y-%m-%d") != date_et:
            continue
        if dt_et.hour == 9 and dt_et.minute == 30:
            return {"high": c["high"], "low": c["low"], "ts": c["timestamp"]}
    return None


def detect_break(candles_1m: list, opening_range: dict, after_ts: int) -> str | None:
    """Return 'long' or 'short' when a 1m candle closes outside the range."""
    for c in candles_1m:
        if c["timestamp"] <= after_ts:
            continue
        if c["close"] > opening_range["high"]:
            return "long"
        if c["close"] < opening_range["low"]:
            return "short"
    return None


def find_fvg(candles_1m: list, opening_range: dict, direction: str,
             after_ts: int, min_gap_pct: float = 0.0) -> dict | None:
    """Return first valid FVG outside the opening range, or None."""
    outside = [c for c in candles_1m if c["timestamp"] > after_ts]

    for i in range(len(outside) - 2):
        c1, c2, c3 = outside[i], outside[i + 1], outside[i + 2]

        if direction == "long":
            all_above = all(c["low"] > opening_range["high"] for c in (c1, c2, c3))
            if all_above and c1["high"] < c3["low"]:
                gap = c3["low"] - c1["high"]
                mid = (c3["low"] + c1["high"]) / 2
                if mid > 0 and gap / mid >= min_gap_pct:
                    return {"c1": c1, "c2": c2, "c3": c3, "direction": "long"}

        elif direction == "short":
            all_below = all(c["high"] < opening_range["low"] for c in (c1, c2, c3))
            if all_below and c1["low"] > c3["high"]:
                gap = c1["low"] - c3["high"]
                mid = (c1["low"] + c3["high"]) / 2
                if mid > 0 and gap / mid >= min_gap_pct:
                    return {"c1": c1, "c2": c2, "c3": c3, "direction": "short"}

    return None


# ── main loop tick ─────────────────────────────────────────────────────────────

async def loop_once(state: dict) -> dict:
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    today = now_et.strftime("%Y-%m-%d")
    p = load_params()

    # Reset daily state on new day
    if state.get("last_trade_date") != today:
        if state.get("current_trade") is None:
            state["traded_today"] = False
            logger.info(f"New trading day: {today}")
        state["last_trade_date"] = today

    # Weekend skip
    if now_et.weekday() >= 5:
        logger.info(f"Weekend — no trading ({now_et.strftime('%A %H:%M')} ET)")
        return state

    hhmm = now_et.hour * 100 + now_et.minute

    if hhmm < 935:
        logger.info(f"Pre-market ({now_et.strftime('%H:%M')} ET) — waiting for 9:35")
        return state

    if hhmm >= p["trade_window_end"] and not state.get("current_trade"):
        logger.info(f"Trading window closed ({now_et.strftime('%H:%M')} ET) — done today")
        return state

    # ── exit check for open trade ─────────────────────────────────────────────
    if state["current_trade"]:
        candles_1m = await fetch_ohlcv(symbol="NQ=F", interval="1m", period="1d")
        if not candles_1m:
            logger.warning("Failed to fetch 1m candles for exit check")
            return state

        trade = state["current_trade"]
        sl, tp = trade["stop_loss"], trade["target"]
        closed = None

        for c in (c for c in candles_1m if c["timestamp"] > trade["entry_ts"]):
            if trade["direction"] == "long":
                if c["high"] >= tp:
                    closed = {**trade, "exit_price": tp, "exit_reason": "tp",
                              "pnl_pct": round((tp - trade["entry_price"]) / trade["entry_price"], 6)}
                    break
                if c["low"] <= sl:
                    closed = {**trade, "exit_price": sl, "exit_reason": "sl",
                              "pnl_pct": round((sl - trade["entry_price"]) / trade["entry_price"], 6)}
                    break
            else:
                if c["low"] <= tp:
                    closed = {**trade, "exit_price": tp, "exit_reason": "tp",
                              "pnl_pct": round((trade["entry_price"] - tp) / trade["entry_price"], 6)}
                    break
                if c["high"] >= sl:
                    closed = {**trade, "exit_price": sl, "exit_reason": "sl",
                              "pnl_pct": round((trade["entry_price"] - sl) / trade["entry_price"], 6)}
                    break

        if closed:
            closed["close_ts"] = int(now_utc.timestamp())
            log_trade(closed)
            logger.info(
                f"Trade CLOSED | {closed['direction']} | entry={closed['entry_price']:.2f} "
                f"exit={closed['exit_price']:.2f} reason={closed['exit_reason']} "
                f"pnl={closed['pnl_pct']*100:.3f}%"
            )
            state["current_trade"] = None
            if reflection_due():
                logger.info("Reflection triggered")
                try:
                    from hermes_trading.reflect import run_reflection
                    run_reflection()
                except Exception as e:
                    logger.error(f"Reflection failed: {e}")
        else:
            logger.info(
                f"Trade OPEN | {trade['direction']} @ {trade['entry_price']:.2f} "
                f"SL={sl:.2f} TP={tp:.2f}"
            )
        return state

    # ── skip if already traded today ──────────────────────────────────────────
    if state.get("traded_today"):
        logger.info(f"Already traded today — standing by ({now_et.strftime('%H:%M')} ET)")
        return state

    # ── fetch data ────────────────────────────────────────────────────────────
    candles_5m, candles_1m = await asyncio.gather(
        fetch_ohlcv(symbol="NQ=F", interval="5m", period="5d"),
        fetch_ohlcv(symbol="NQ=F", interval="1m", period="1d"),
    )

    if not candles_5m or not candles_1m:
        logger.warning("Candle fetch returned empty — skipping")
        return state

    # ── opening range ─────────────────────────────────────────────────────────
    opening_range = get_opening_range(candles_5m, today)
    if not opening_range:
        logger.info(f"9:30 opening range not found yet ({now_et.strftime('%H:%M')} ET)")
        return state

    logger.info(f"Opening range H={opening_range['high']:.2f} L={opening_range['low']:.2f}")

    range_close_ts = opening_range["ts"] + 300  # 9:30 candle closes at 9:35

    # ── break detection ───────────────────────────────────────────────────────
    direction = detect_break(candles_1m, opening_range, after_ts=range_close_ts)
    if not direction:
        logger.info("Waiting for range break...")
        return state

    logger.info(f"Range break: {direction.upper()}")

    # ── FVG scan ──────────────────────────────────────────────────────────────
    fvg = find_fvg(candles_1m, opening_range, direction,
                   after_ts=range_close_ts, min_gap_pct=p["fvg_min_gap_pct"])
    if not fvg:
        logger.info(f"Break={direction} confirmed — no FVG yet, watching...")
        return state

    c1, c3 = fvg["c1"], fvg["c3"]
    entry = c3["close"]
    buf = p["sl_buffer_pct"]

    if direction == "long":
        sl = c1["high"] * (1 - buf)
        risk = entry - sl
    else:
        sl = c1["low"] * (1 + buf)
        risk = sl - entry

    if risk <= 0:
        logger.warning("FVG risk <= 0 — skipping")
        return state

    tp = entry + risk * p["rr_ratio"] if direction == "long" else entry - risk * p["rr_ratio"]
    gap_pts = (c3["low"] - c1["high"]) if direction == "long" else (c1["low"] - c3["high"])

    new_trade = {
        "direction": direction,
        "entry_price": round(entry, 2),
        "stop_loss": round(sl, 2),
        "target": round(tp, 2),
        "entry_ts": c3["timestamp"],
        "open_ts": int(now_utc.timestamp()),
        "mode": "paper",
        "fvg_gap_pts": round(gap_pts, 2),
    }
    state["current_trade"] = new_trade
    state["traded_today"] = True
    logger.info(
        f"ENTRY | {direction} @ {entry:.2f} SL={sl:.2f} TP={tp:.2f} "
        f"gap={gap_pts:.2f}pts R:R={p['rr_ratio']}"
    )
    return state


async def loop_forever() -> None:
    logger.info("Booting hermes-trading worker | MNQ-5M-Candle | paper mode")
    logger.info("Strategy: 9:30 ET opening range + 1m FVG breakout")

    state = load_state()
    tick = 0

    while True:
        tick += 1
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] Tick {tick}")
        try:
            state = await loop_once(state)
            save_state(state)
        except Exception as e:
            logger.error(f"Tick error: {e}", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)
