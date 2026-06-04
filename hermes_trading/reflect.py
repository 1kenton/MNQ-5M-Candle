"""
Reflection cycle: analyzes trades and proposes ONE strategy change.
Two modes:
  - --fallback: deterministic rule (before Hermes is installed)
  - --hermes: calls Hermes subprocess for intelligent reflection
"""
import argparse
import json
import yaml
import sys
from pathlib import Path
from datetime import datetime
from score import load_goal, score

def load_trades(trades_path: str = "state/trades.jsonl") -> list:
    """Load all trades from jsonl"""
    trades = []
    if not Path(trades_path).exists():
        return trades
    with open(trades_path) as f:
        for line in f:
            if line.strip():
                trades.append(json.loads(line))
    return trades


def load_strategy(strategy_path: str = "state/strategy.yaml") -> dict:
    """Load current strategy"""
    with open(strategy_path) as f:
        return yaml.safe_load(f)


def save_strategy(strategy: dict, strategy_path: str = "state/strategy.yaml"):
    """Save strategy back"""
    with open(strategy_path, "w") as f:
        yaml.dump(strategy, f, default_flow_style=False)


def next_version(current_version: str) -> str:
    """Bump version: "01" -> "02" """
    try:
        num = int(current_version)
        return f"{num + 1:02d}"
    except:
        return "02"


def reflect_fallback(trades: list, goal: dict, strategy: dict) -> dict:
    """
    Deterministic fallback reflection (before Hermes).
    
    Rule: if realised return < target, loosen entry threshold.
           if drawdown > max, tighten stop loss.
    Always changes exactly ONE variable.
    """
    if not trades:
        return {"change": "none", "reason": "no trades yet"}
    
    # Score current trades
    composite = score(trades, goal)
    
    # Simple heuristic
    if composite < -0.2:  # underperforming
        # Loosen entry (make it less strict)
        hypothesis = {
            "timestamp": datetime.now().isoformat(),
            "prior_version": strategy.get("version", "01"),
            "variable": "entry.threshold (if applicable)",
            "action": "loosen",
            "reason": "Return underperforming; relax entry selectivity",
            "composite_score": composite
        }
        # For now, we can't change because this strategy doesn't have a simple threshold.
        # In a real scenario, we'd adjust the fair_value_gap tolerance or market_time window.
        return hypothesis
    else:
        # Tighten stop loss
        hypothesis = {
            "timestamp": datetime.now().isoformat(),
            "prior_version": strategy.get("version", "01"),
            "variable": "exit.risk_reward_ratio",
            "action": "tighten",
            "reason": "Reducing risk per trade to stay below max drawdown",
            "composite_score": composite
        }
        return hypothesis


def reflect_hermes(trades: list, goal: dict, strategy: dict) -> dict:
    """
    Call Hermes subprocess for intelligent reflection.
    (Implemented in Phase 7)
    """
    pass


def main():
    parser = argparse.ArgumentParser(description="Trading strategy reflection")
    parser.add_argument("--fallback", action="store_true", help="Use deterministic fallback")
    parser.add_argument("--hermes", action="store_true", help="Use Hermes subprocess")
    args = parser.parse_args()
    
    # Load data
    trades = load_trades()
    goal = load_goal()
    strategy = load_strategy()
    
    # Reflect
    if args.fallback:
        hypothesis = reflect_fallback(trades, goal, strategy)
    elif args.hermes:
        hypothesis = reflect_hermes(trades, goal, strategy)
    else:
        print("Usage: python reflect.py --fallback | --hermes")
        sys.exit(1)
    
    # Bump version
    old_version = strategy.get("version", "01")
    new_version = next_version(old_version)
    
    # Save prior version to history
    history_dir = Path("state/history")
    history_dir.mkdir(exist_ok=True)
    with open(history_dir / f"v{old_version}.yaml", "w") as f:
        yaml.dump(strategy, f)
    
    # Append hypothesis to hypotheses.jsonl
    with open("state/hypotheses.jsonl", "a") as f:
        hypothesis["version"] = new_version
        f.write(json.dumps(hypothesis) + "\n")
    
    # Update strategy (stub for now)
    strategy["version"] = new_version
    save_strategy(strategy)
    
    print(f"✓ Reflected. v{old_version} → v{new_version}")
    print(f"  Hypothesis: {hypothesis['variable']} → {hypothesis['action']}")


if __name__ == "__main__":
    main()
