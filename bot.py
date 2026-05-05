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
API_URL       = "http://51.77.216.195/crapi/lamix/viewstats"
POLL_SECONDS  = 1
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
            records = data.get("data", [])
            log.info("API fetched %d records", len(records))
            return records
        log.warning("API error: %s", data.get("msg", "unknown"))
    except Exception as e:
        log.error("fetch_otps failed: %s", e)
    return []


def extract_otp(message: str) -> str:
    if not message:
        return None
    pattern_keyword = r'(?:otp|code|verification code|verify|pin|password|token)[^\d]*(\d{4,8})'
    match = re.search(pattern_keyword, message, re.IGNORECASE)
    if match:
        return match.group(1)
    pattern_is = r'(?:is|:|are)[^\d]*(\d{4,8})'
    match = re.search(pattern_is, message, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'\b(\d{4,8})\b', message)
    if match:
        return match.group(1)
    return None


def format_message(entry: dict) -> str:
    raw_message = entry.get("message", "N/A")
    otp = extract_otp(raw_message)

    otp_section = (
        f"🔐 <b>OTP Detected:</b>\n"
        f"➡️  <code>{otp}</code>\n\n"
    ) if otp else ""

    return (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>New Message Arrived</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Service:</b>  {entry.get('cli', 'N/A')}\n"
        f"📞 <b>Number:</b>  <code>{entry.get('num', 'N/A')}</code>\n\n"
        f"{otp_section}"
        f"💬 <b>Full Message:</b>\n"
        f"{raw_message}\n\n"
        f"🕒 <b>Time:</b>  {entry.get('dt', 'N/A')}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <i>Auto-detected &amp; delivered instantly</i>\n"
        "🤖 <i>Bot: WITHIN SMS</i>"
    )


def send_telegram(text: str, copy_text: str = None) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHANNEL_ID,
        "text":       text,
        "parse_mode": "HTML",
    }
    if copy_text:
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {
                    "text": "🤍 Copy OTP",
                    "copy_text": {"text": copy_text}
                }
            ]]
        }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error("Telegram send failed: %s | response: %s", e,
                  getattr(e, 'response', None) and e.response.text)
        return False


def fingerprint(entry: dict) -> str:
    # Strip whitespace to avoid mismatch issues
    dt  = str(entry.get("dt", "")).strip()
    num = str(entry.get("num", "")).strip()
    msg = str(entry.get("message", "")).strip()
    return f"{dt}|{num}|{msg}"


def main():
    log.info("🤖 Bot started. Polling every %ds ...", POLL_SECONDS)

    # Startup test — confirm bot can send to channel
    ok = send_telegram("🤖 <b>WITHIN SMS Bot started!</b>\n⚡ Listening for new OTPs...")
    log.info("Startup message sent: ok=%s", ok)

    # Prime existing records — don't send old OTPs
    initial = fetch_otps()
    for entry in initial:
        seen.add(fingerprint(entry))
    log.info("Primed %d existing records. Seen set size: %d", len(initial), len(seen))

    while True:
        time.sleep(POLL_SECONDS)
        records = fetch_otps()

        new = [r for r in records if fingerprint(r) not in seen]
        log.info("Total: %d | New: %d | Seen: %d", len(records), len(new), len(seen))

        if new:
            for entry in reversed(new):
                otp = extract_otp(entry.get("message", ""))
                ok  = send_telegram(
                    text=format_message(entry),
                    copy_text=otp
                )
                seen.add(fingerprint(entry))
                log.info("✅ Sent | dt=%s | num=%s | otp=%s | ok=%s",
                         entry.get("dt"), entry.get("num"), otp, ok)


if __name__ == "__main__":
    main()
