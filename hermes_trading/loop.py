"""
Main loop: every 60 seconds, fetch price data, evaluate strategy, take trades.
Runs forever (or until stopped). Circuit-breaker after 5 consecutive failures.
"""
import asyncio
import json
import yaml
import os
from datetime import datetime
from pathlib import Path
from hermes_trading.adapters.price import fetch as fetch_price


def load_strategy(strategy_path: str = "state/strategy.yaml") -> dict:
    with open(strategy_path) as f:
        return yaml.safe_load(f)


def log_trade(trade: dict, trades_path: str = "state/trades.jsonl"):
    """Append trade to jsonl"""
    with open(trades_path, "a") as f:
        f.write(json.dumps(trade) + "\n")


def log_heartbeat(heartbeat: dict, heartbeat_path: str = "state/heartbeat.json"):
    """Write heartbeat"""
    with open(heartbeat_path, "w") as f:
        json.dump(heartbeat, f)


async def evaluate_one_candle_setup(price_data: dict) -> dict:
    """
    Evaluate the one-candle-breakout setup.
    
    For now, returns a mock trade (paper mode).
    In a real implementation, this would:
      1. Check if we're at 9:30 ET
      2. Extract 5m and 1m candles
      3. Detect breakout + FVG
      4. Generate entry/exit prices
      5. Return a trade dict
    """
    # Mock trade
    trade = {
        "timestamp": datetime.now().isoformat(),
        "entry_price": 17500.0,
        "exit_price": 17550.0,
        "direction": "long",
        "stop_loss": 17480.0,
        "target": 17550.0,
        "pnl": 500.0,
        "reason": "FVG breakout detected (mock)"
    }
    return trade


async def loop_forever():
    """Main loop: tick every 60 seconds."""
    consecutive_failures = 0
    tick = 0
    
    while True:
        tick += 1
        now = datetime.now()
        
        try:
            print(f"[{now.isoformat()}] Tick {tick}: fetching price data...")
            
            # Fetch price
            price_data = await fetch_price()
            consecutive_failures = 0  # reset on success
            
            # Evaluate strategy
            strategy = load_strategy()
            trade = await evaluate_one_candle_setup(price_data)
            
            # Log if paper mode
            mode = os.getenv("HERMES_TRADING_MODE", "paper")
            if mode == "paper":
                log_trade(trade)
                print(f"  Paper trade logged: {trade['direction']} @ {trade['entry_price']}")
            
            # Heartbeat
            log_heartbeat({
                "tick": tick,
                "timestamp": now.isoformat(),
                "status": "ok",
                "trades_logged": 1
            })
            
        except Exception as e:
            consecutive_failures += 1
            print(f"  ERROR (attempt {consecutive_failures}/5): {e}")
            
            if consecutive_failures >= 5:
                print("Circuit-breaker triggered. Exiting.")
                break
        
        # Wait 60s before next tick
        await asyncio.sleep(60)


if __name__ == "__main__":
    # Ensure state dir exists
    Path("state").mkdir(exist_ok=True)
    
    # Boot message
    print("Booting hermes-trading worker")
    print(f"  Mode: {os.getenv('HERMES_TRADING_MODE', 'paper')}")
    print(f"  Asset: MNQ")
    print(f"  Strategy: one-candle-breakout")
    print("")
    
    asyncio.run(loop_forever())
