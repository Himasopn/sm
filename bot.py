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
    """
    SMS se OTP automatically detect karta hai.
    Pehle keyword ke paas wala number dhundhta hai,
    phir fallback mein koi bhi 4-8 digit number.
    """
    if not message:
        return None

    # Strategy 1: OTP/code/verification keyword ke baad wala number
    pattern_keyword = r'(?:otp|code|verification code|verify|pin|password|token)[^\d]*(\d{4,8})'
    match = re.search(pattern_keyword, message, re.IGNORECASE)
    if match:
        return match.group(1)

    # Strategy 2: "is" ya ":" ke baad wala number
    pattern_is = r'(?:is|:|are)[^\d]*(\d{4,8})'
    match = re.search(pattern_is, message, re.IGNORECASE)
    if match:
        return match.group(1)

    # Strategy 3: Fallback — koi bhi 4-8 digit standalone number
    match = re.search(r'\b(\d{4,8})\b', message)
    if match:
        return match.group(1)

    return None


def format_message(entry: dict) -> str:
    raw_message = entry.get("message", "N/A")
    otp = extract_otp(raw_message)

    # OTP wala section — detect hua toh highlight, nahi toh skip
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
                    "text": "📋 Copy OTP",
                    "copy_text": {"text": copy_text}
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

    initial = fetch_otps()
    for entry in initial:
        seen.add(fingerprint(entry))
    log.info("Primed %d existing records. Waiting for new messages...", len(seen))

    while True:
        time.sleep(POLL_SECONDS)
        records = fetch_otps()

        new = [r for r in records if fingerprint(r) not in seen]

        if new:
            for entry in reversed(new):
                otp = extract_otp(entry.get("message", ""))
                ok  = send_telegram(
                    text=format_message(entry),
                    copy_text=otp  # OTP mila toh copy button mein wahi, nahi toh button nahi aayega
                )
                seen.add(fingerprint(entry))
                log.info("Sent | dt=%s | num=%s | otp=%s | ok=%s",
                         entry.get("dt"), entry.get("num"), otp, ok)
        else:
            log.debug("No new messages.")


if __name__ == "__main__":
    main()
