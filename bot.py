import os
import time
import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── ENV VARS ──────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID   = os.environ["TELEGRAM_CHANNEL_ID"]
CR_API_TOKEN = os.environ["CR_API_TOKEN"]

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
API_URL       = "http://147.135.212.197/crapi/time/viewstats"
POLL_SECONDS  = 5
FETCH_RECORDS = 50

# ── STATE ─────────────────────────────────────────────────────────────────────
seen: set = set()   # fingerprints of already-sent OTPs


def fetch_otps() -> list:
    """Fetch latest records from CR API — no date filter needed."""
    params = {
        "token":   CR_API_TOKEN,
        "records": FETCH_RECORDS,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success":
            return data.get("data", [])
        log.warning("API error: %s", data.get("msg", "unknown"))
    except Exception as e:
        log.error("fetch_otps failed: %s", e)
    return []


def send_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":    CHANNEL_ID,
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def fingerprint(entry: dict) -> str:
    return f"{entry.get('dt')}|{entry.get('num')}|{entry.get('message')}"


def format_message(entry: dict) -> str:
    return (
        "📩 <b>New OTP</b>\n"
        f"🕐 <b>Time:</b> {entry.get('dt', 'N/A')}\n"
        f"📱 <b>Number:</b> <code>{entry.get('num', 'N/A')}</code>\n"
        f"🔖 <b>Sender:</b> {entry.get('cli', 'N/A')}\n"
        f"💬 <b>Message:</b> {entry.get('message', 'N/A')}\n"
        f"💰 <b>Payout:</b> {entry.get('payout', 'N/A')}"
    )


def main():
    log.info("🤖 Bot started. Polling every %ds ...", POLL_SECONDS)

    # ── Prime on startup: mark existing records as seen, don't send them ──────
    initial = fetch_otps()
    for entry in initial:
        seen.add(fingerprint(entry))
    log.info("Primed %d existing records. Waiting for new OTPs...", len(seen))

    # ── Main poll loop ─────────────────────────────────────────────────────────
    while True:
        time.sleep(POLL_SECONDS)
        records = fetch_otps()

        new = [r for r in records if fingerprint(r) not in seen]

        if new:
            for entry in reversed(new):   # oldest first
                fp = fingerprint(entry)
                ok = send_telegram(format_message(entry))
                seen.add(fp)
                log.info("Sent OTP | dt=%s | num=%s | ok=%s",
                         entry.get("dt"), entry.get("num"), ok)
        else:
            log.debug("No new OTPs.")


if __name__ == "__main__":
    main()
