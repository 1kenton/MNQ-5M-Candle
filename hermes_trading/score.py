"""
Scoring function: evaluates trade outcomes against goal.yaml
Returns composite score in [-1, +1]
"""
import yaml
import numpy as np


def load_goal(goal_path: str = "state/goal.yaml") -> dict:
    """Load goal.yaml"""
    with open(goal_path) as f:
        return yaml.safe_load(f)


def score(trades: list, goal: dict) -> float:
    """
    Composite score of trades against goal.
    
    Inputs:
      - trades: list of trade dicts with keys: entry_price, exit_price, entry_time, exit_time, direction
      - goal: dict with target_return_30d, max_drawdown, min_sharpe, failure_below
    
    Returns:
      - float in [-1, +1]: 0 = goal, >0 = beating goal, <0 = below goal
    """
    if not trades:
        return 0.0
    
    # Calculate realised return
    pnl = sum([t.get("pnl", 0) for t in trades])
    realised_return = pnl / 10000  # assume 10k account
    target_return = goal["target_return_30d"]
    return_score = (realised_return - target_return) / abs(target_return)
    
    # Calculate drawdown
    cumulative = np.cumsum([t.get("pnl", 0) for t in trades])
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (running_max - cumulative) / (running_max + 1e-6)
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0
    max_drawdown_goal = goal["max_drawdown"]
    dd_score = (max_drawdown_goal - max_dd) / max_drawdown_goal if max_drawdown_goal > 0 else 0
    
    # Calculate Sharpe
    if len(cumulative) > 1:
        returns = np.diff(cumulative)
        sharpe = np.mean(returns) / (np.std(returns) + 1e-6)
    else:
        sharpe = 0
    min_sharpe_goal = goal["min_sharpe"]
    sharpe_score = (sharpe - min_sharpe_goal) / max(min_sharpe_goal, 1)
    
    # Composite
    composite = (return_score + dd_score + sharpe_score) / 3
    composite = np.clip(composite, -1, 1)
    
    return composite


if __name__ == "__main__":
    goal = load_goal()
    trades = [
        {"entry_price": 17500, "exit_price": 17550, "pnl": 500, "entry_time": 0, "exit_time": 1},
        {"entry_price": 17550, "exit_price": 17530, "pnl": -200, "entry_time": 2, "exit_time": 3},
    ]
    print(f"Score: {score(trades, goal)}")
