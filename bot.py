import os
import re
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
seen: set = set()


def fetch_otps() -> list:
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


def extract_otp(message: str) -> str:
    """Message se OTP/code extract karta hai."""
    match = re.search(r'\b(\d{4,8})\b', message or "")
    return match.group(1) if match else "N/A"


def format_message(entry: dict) -> str:
    otp = extract_otp(entry.get("message", ""))
    return (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>New OTP Arrived</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Service:</b>  {entry.get('cli', 'N/A')}\n"
        f"📞 <b>Number:</b>  <code>{entry.get('num', 'N/A')}</code>\n\n"
        "🔐 <b>Your OTP:</b>\n"
        f"➡️  <code>{otp}</code>\n\n"
        f"🕒 <b>Time:</b>  {entry.get('dt', 'N/A')}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <i>Auto-detected &amp; delivered instantly</i>\n"
        "🤖 <i>Bot: WITHIN SMS</i>"
    )


def send_telegram(text: str, otp: str = None) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHANNEL_ID,
        "text":       text,
        "parse_mode": "HTML",
    }
    if otp and otp != "N/A":
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {
                    "text": "📋 Copy OTP",
                    "copy_text": {"text": otp}
                }
            ]]
        }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False


def fingerprint(entry: dict) -> str:
    return f"{entry.get('dt')}|{entry.get('num')}|{entry.get('message')}"


def main():
    log.info("🤖 Bot started. Polling every %ds ...", POLL_SECONDS)

    # Startup pe existing records prime karo, bhejo mat
    initial = fetch_otps()
    for entry in initial:
        seen.add(fingerprint(entry))
    log.info("Primed %d existing records. Waiting for new OTPs...", len(seen))

    while True:
        time.sleep(POLL_SECONDS)
        records = fetch_otps()

        new = [r for r in records if fingerprint(r) not in seen]

        if new:
            for entry in reversed(new):  # oldest first
                otp = extract_otp(entry.get("message", ""))
                ok  = send_telegram(format_message(entry), otp=otp)
                seen.add(fingerprint(entry))
                log.info("Sent | dt=%s | num=%s | otp=%s | ok=%s",
                         entry.get("dt"), entry.get("num"), otp, ok)
        else:
            log.debug("No new OTPs.")


if __name__ == "__main__":
    main()
