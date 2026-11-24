"""SYN signal receiver.

TradingView alert (webhook)  ->  this service  ->  Discord channel,
posted with your existing SYN bot's token so it shows up as that bot.

Environment variables (set them in Railway):
  DISCORD_BOT_TOKEN   token of your existing basic SYN bot
  SIGNAL_CHANNEL_ID   channel the signals should be posted in
  WEBHOOK_SECRET      any long random string; must match the Pine script input
"""
import hmac
import logging
import os
import threading
import time

import requests
from flask import Flask, jsonify, request

from embed import build_embed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("syn")

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID = os.environ["SIGNAL_CHANNEL_ID"]
SECRET = os.environ["WEBHOOK_SECRET"]

DISCORD_URL = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

app = Flask(__name__)

_seen: dict = {}
_seen_lock = threading.Lock()


def _is_duplicate(key: tuple) -> bool:
    """TradingView can retry a webhook; ignore the same signal seen within 2 minutes."""
    now = time.time()
    with _seen_lock:
        for k in [k for k, t in _seen.items() if now - t > 120]:
            del _seen[k]
        if key in _seen:
            return True
        _seen[key] = now
        return False


def _post_to_discord(embed: dict) -> None:
    for attempt in range(3):
        try:
            r = requests.post(DISCORD_URL, headers=HEADERS,
                              json={"embeds": [embed]}, timeout=10)
        except requests.RequestException as exc:
            log.error("Discord request failed: %s", exc)
            time.sleep(1)
            continue
        if r.status_code == 429:
            wait = float(r.json().get("retry_after", 1))
            log.warning("Rate limited, waiting %.1fs", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 300:
            log.error("Discord returned %s: %s", r.status_code, r.text[:300])
        else:
            log.info("Signal posted")
        return


@app.get("/")
def health():
    return "SYN receiver is running", 200


@app.post("/tv")
def tradingview():
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify(error="body must be JSON"), 400

    if not hmac.compare_digest(str(data.get("secret", "")), SECRET):
        log.warning("Rejected request with bad secret")
        return jsonify(error="forbidden"), 403

    try:
        side = str(data["side"]).lower()
        entry = float(data["entry"])
        stop = float(data["stop"])
    except (KeyError, ValueError, TypeError):
        return jsonify(error="need side, entry, stop"), 400

    if side not in ("long", "short"):
        return jsonify(error="side must be long or short"), 400
    if (side == "long" and stop >= entry) or (side == "short" and stop <= entry):
        return jsonify(error="stop is on the wrong side of entry"), 400

    symbol = str(data.get("symbol", "NQ"))
    tf = str(data.get("tf", "1"))
    # Pine sends milliseconds; fall back to "now" if it is missing.
    t_ms = data.get("t")
    ts = int(float(t_ms) / 1000) if t_ms else int(time.time())

    if _is_duplicate((side, round(entry, 2), ts // 60)):
        return jsonify(status="duplicate ignored"), 200

    embed = build_embed(side, symbol, tf, entry, stop, ts)
    # TradingView gives up after ~3 seconds, so answer now and post in the background.
    threading.Thread(target=_post_to_discord, args=(embed,), daemon=True).start()
    return jsonify(status="ok"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
