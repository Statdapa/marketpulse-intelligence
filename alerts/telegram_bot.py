"""
Telegram alert bot — proactive push notifications for anomalies.

Sends formatted alerts to a configured Telegram chat when:
  - Arbitrage signal detected (spread divergence > threshold)
  - Regulatory filing spike (> N filings in 1h)
  - Sentiment shift (±15pts in 1h)
  - Spread anomaly (exchange spread > 2× average)

Uses the Telegram Bot API directly (no library dep) via aiohttp.
"""
import logging
import asyncio
from datetime import datetime
from aiohttp import ClientSession
from config.settings import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

# Track sent alerts to avoid duplicates (reset every hour)
_sent_hashes: set = set()
_last_reset = datetime.utcnow()


def _dedup_hash(anomaly: dict) -> str:
    return f"{anomaly.get('type','')}_{anomaly.get('description','')[:60]}"


def _reset_dedup_if_stale():
    global _sent_hashes, _last_reset
    now = datetime.utcnow()
    if (now - _last_reset).seconds > 3600:
        _sent_hashes.clear()
        _last_reset = now


def _format_alert(anomaly: dict) -> str:
    """Format an anomaly dict into a Telegram HTML message."""
    type_ = anomaly.get("type", "unknown")
    severity = anomaly.get("severity", "medium").upper()
    desc = anomaly.get("description", "")
    ts = anomaly.get("ts", datetime.utcnow().isoformat())[:19]

    emoji = {
        "arbitrage": "⚡",
        "spread_anomaly": "📊",
        "sentiment_shift": "📡",
        "filing_spike": "⚖️",
        "job_surge": "💼",
    }.get(type_, "🔔")

    severity_tag = {
        "HIGH": "🔴",
        "MEDIUM": "🟡",
        "LOW": "🟢",
    }.get(severity, "⚪")

    data = anomaly.get("data", {})
    extra = ""

    if type_ == "arbitrage":
        extra = (
            f"\n💰 <b>Buy:</b> {data.get('buy_exchange','').upper()} @ ${data.get('buy_price',0):,.2f}"
            f"\n💰 <b>Sell:</b> {data.get('sell_exchange','').upper()} @ ${data.get('sell_price',0):,.2f}"
            f"\n📈 <b>Arb/BTC:</b> ${data.get('arb_per_btc',0):,.2f}"
        )
    elif type_ == "spread_anomaly":
        extra = (
            f"\n📊 <b>Current:</b> {data.get('current_spread_pct',0):.3f}%"
            f"\n📊 <b>Average:</b> {data.get('avg_spread_pct',0):.3f}%"
            f"\n📊 <b>Ratio:</b> {data.get('multiplier',0):.1f}×"
        )
    elif type_ == "sentiment_shift":
        arrow = "📈" if data.get("shift", 0) > 0 else "📉"
        extra = (
            f"\n{arrow} <b>{data.get('platform','').upper()} {data.get('symbol','')}:</b>"
            f" {data.get('from_score',0):.0f}% → {data.get('to_score',0):.0f}%"
            f" ({data.get('shift',0):+.1f}pts)"
        )
    elif type_ == "filing_spike":
        extra = (
            f"\n📁 <b>Regulator:</b> {data.get('source','')}"
            f"\n📁 <b>Count:</b> {data.get('count',0)} filings in last hour"
        )

    return (
        f"{emoji} <b>MarketPulse Alert</b> {severity_tag}\n"
        f"<code>{type_.replace('_',' ').upper()}</code>\n\n"
        f"{desc}{extra}\n\n"
        f"<i>🕐 {ts} UTC</i>"
    )


async def send_alert(anomaly: dict) -> bool:
    """Send a single anomaly alert to Telegram. Returns True on success."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — skipping alert")
        return False

    _reset_dedup_if_stale()
    h = _dedup_hash(anomaly)
    if h in _sent_hashes:
        return False  # duplicate
    _sent_hashes.add(h)

    message = _format_alert(anomaly)
    try:
        async with ClientSession() as session:
            async with session.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Telegram alert sent: {anomaly.get('type')}")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"Telegram API error {resp.status}: {body}")
                    return False
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")
        return False


async def flush_new_anomalies():
    """
    Compare current anomaly list against sent hashes,
    dispatch any new ones to Telegram.
    """
    from data.store import store
    async with store._lock:
        anomalies = store.anomalies[:20]

    tasks = [send_alert(a) for a in anomalies]
    results = await asyncio.gather(*tasks)
    sent = sum(1 for r in results if r)
    if sent:
        logger.info(f"Telegram: dispatched {sent} new alerts")
    return sent


async def send_startup_message():
    """Notify the Telegram channel that MarketPulse has started."""
    await send_alert({
        "type": "system",
        "severity": "low",
        "description": "MarketPulse Intelligence system started. Monitoring active.",
        "data": {},
        "ts": datetime.utcnow().isoformat()
    })
