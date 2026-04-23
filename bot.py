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
BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]   # set in Heroku Config Vars
CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]  # numeric id e.g. -1001234567890
CR_API_TOKEN = os.environ.get("CR_API_TOKEN", "R1dPNEVBlIlFb3Rvggja2uNf3eMi3pfU3GMfFqBkGmGjGiLZoo=")

# ── CONSTANTS ─────────────────────────────────────────────────────────────────
API_URL      = "http://147.135.212.197/crapi/time/viewstats"
POLL_SECONDS = 5
FETCH_RECORDS = 50   # how many latest records to check each cycle

# ── STATE ─────────────────────────────────────────────────────────────────────
seen_ids: set = set()   # stores "dt|num|message" fingerprints already sent

# ── HELPERS ───────────────────────────────────────────────────────────────────

def fetch_otps() -> list[dict]:
    """Pull latest records from the CR API."""
    params = {
        "token":   CR_API_TOKEN,
        "records": FETCH_RECORDS,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success":
            return data.get("data", [])
        else:
            log.warning("API error: %s", data.get("msg", "unknown"))
    except Exception as e:
        log.error("fetch_otps error: %s", e)
    return []


def send_telegram(text: str) -> bool:
    """Send a message to the configured Telegram channel."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHANNEL_ID,
        "text":       text,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error("send_telegram error: %s", e)
        return False


def make_fingerprint(entry: dict) -> str:
    return f"{entry.get('dt')}|{entry.get('num')}|{entry.get('message')}"


def format_message(entry: dict) -> str:
    return (
        f"📩 <b>New OTP Received</b>\n"
        f"🕐 <b>Time:</b> {entry.get('dt', 'N/A')}\n"
        f"📱 <b>Number:</b> <code>{entry.get('num', 'N/A')}</code>\n"
        f"🔖 <b>Sender:</b> {entry.get('cli', 'N/A')}\n"
        f"💬 <b>Message:</b> {entry.get('message', 'N/A')}\n"
        f"💰 <b>Payout:</b> {entry.get('payout', 'N/A')}"
    )


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def main():
    log.info("Bot started. Polling every %ds …", POLL_SECONDS)

    # ── Prime the seen-set on first run so we don't spam old messages ──────────
    initial = fetch_otps()
    for entry in initial:
        seen_ids.add(make_fingerprint(entry))
    log.info("Primed with %d existing records.", len(seen_ids))

    while True:
        time.sleep(POLL_SECONDS)
        records = fetch_otps()

        new_entries = []
        for entry in records:
            fp = make_fingerprint(entry)
            if fp not in seen_ids:
                new_entries.append(entry)
                seen_ids.add(fp)

        if new_entries:
            # send oldest first
            for entry in reversed(new_entries):
                text = format_message(entry)
                ok = send_telegram(text)
                log.info("Sent OTP to channel: %s (ok=%s)", entry.get("dt"), ok)
        else:
            log.debug("No new OTPs.")


if __name__ == "__main__":
    main()
