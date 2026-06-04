"""
Entrypoint. Parses --asset flag (default: MNQ from goal.yaml). Starts the loop.
"""
import sys
import asyncio
from hermes_trading.loop import loop_forever


if __name__ == "__main__":
    # For now, just start the loop
    # Future: parse --asset flag to override goal.yaml
    asyncio.run(loop_forever())
