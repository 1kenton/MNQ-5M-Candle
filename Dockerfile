FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
COPY pyproject.toml ./
COPY hermes_trading ./hermes_trading
RUN /root/.local/bin/uv sync
# Initialize state directory with bootstrap files
RUN mkdir -p /app/state/history && \
    echo 'asset: "MNQ"\ntarget_return_30d: 0.10\nmax_drawdown: 0.08\nmin_sharpe: 1.2\nfailure_below: -0.04\nreflection_every: 5\none_variable_only: true' > /app/state/goal.yaml && \
    echo 'version: "01"\nentry:\n  setup: "one_candle_breakout"\n  market_time: "09:30"\n  timeframe_setup: "5m"\n  timeframe_entry: "1m"\n  fair_value_gap: true\nexit:\n  risk_reward_ratio: 2.0\n  stop_loss_type: "fvg_bottom"' > /app/state/strategy.yaml && \
    touch /app/state/trades.jsonl /app/state/hypotheses.jsonl
ENV HERMES_TRADING_MODE=paper
CMD ["/root/.local/bin/uv", "run", "python", "-m", "hermes_trading.run"]
