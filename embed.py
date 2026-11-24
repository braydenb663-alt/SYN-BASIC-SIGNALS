"""Builds the SYN signal embed (same layout as the SYN Levels post).

Pure Python, no web framework, so it can be tested on its own.
"""
from datetime import datetime, timezone

TICK = 0.25          # NQ / MNQ tick size
NQ_POINT = 20.0      # $ per point, NQ
MNQ_POINT = 2.0      # $ per point, MNQ
GREEN = 0x2ECC71
RED = 0xE74C3C


def snap(price: float) -> float:
    """Round to the nearest NQ tick."""
    return round(price / TICK) * TICK


def fmt(price: float) -> str:
    return f"{price:.2f}"


def pretty_tf(tf: str) -> str:
    """TradingView sends '1', '5', '60', '240', '1D' ... -> '1m', '5m', '1h', '4h', '1D'."""
    tf = str(tf).strip()
    if tf.isdigit():
        mins = int(tf)
        if mins % 60 == 0:
            return f"{mins // 60}h"
        return f"{mins}m"
    return tf


def build_embed(side: str, symbol: str, tf: str, entry: float, stop: float,
                signal_ts: int) -> dict:
    """side: 'long' or 'short'. signal_ts: unix seconds."""
    long_ = side == "long"
    direction = 1 if long_ else -1
    risk = abs(entry - stop)

    targets = [snap(entry + direction * risk * r) for r in (1, 2, 3)]
    tp_lines = "\n".join(
        f"TP{i} `{fmt(tp)}` ({i}R)" for i, tp in enumerate(targets, start=1)
    )

    title = f"{'▲ Bullish' if long_ else '▼ Bearish'} SYN · {symbol.upper()}"

    return {
        "title": title,
        "color": GREEN if long_ else RED,
        "fields": [
            {"name": "Price", "value": f"`{fmt(entry)}`", "inline": True},
            {"name": "Signal time",
             "value": f"<t:{signal_ts}:t> (<t:{signal_ts}:R>)", "inline": True},
            {"name": "Chart", "value": f"`{pretty_tf(tf)}`", "inline": True},
            {"name": "Entry", "value": f"`{fmt(entry)}`", "inline": True},
            {"name": "Stop", "value": f"`{fmt(stop)}`", "inline": True},
            {"name": "Targets", "value": tp_lines, "inline": True},
            {"name": "Risk",
             "value": (f"{risk:.2f} pts · ${risk * NQ_POINT:,.0f} per NQ · "
                       f"${risk * MNQ_POINT:,.0f} per MNQ"),
             "inline": False},
        ],
        # No data-age / data-source note on purpose.
        "footer": {"text": "not financial advice"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
