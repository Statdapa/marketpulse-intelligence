"""
Anomaly detection engine.

Runs after each scrape cycle to detect:
  1. SPREAD ANOMALY   — exchange spread > 2× its 30-day rolling average
  2. ARBITRAGE SIGNAL — price divergence > 0.2% between any two exchanges
  3. SENTIMENT SHIFT  — sentiment moves ±15 points in last 5 readings
  4. FILING SPIKE     — >5 filings from one regulator within 1 hour
  5. JOB SURGE        — compliance hiring up >50% vs 30-day baseline

Each anomaly is:
  - stored in SignalStore
  - dispatched to the Telegram alert bot
  - logged for RAG context
"""
import logging
import statistics
from datetime import datetime, timedelta
from data.store import store
from config.settings import settings

logger = logging.getLogger(__name__)


async def detect_spread_anomalies():
    """Flag exchanges where current spread >> historical average."""
    anomalies = []
    async with store._lock:
        for exchange, symbols in store.exchange_prices.items():
            for symbol, tick in symbols.items():
                history = list(store.spread_history.get(exchange, []))
                if len(history) < 10:
                    continue
                spreads = [h["spread_pct"] for h in history[:-1]]  # exclude current
                if not spreads:
                    continue
                avg = statistics.mean(spreads)
                current = tick["spread_pct"]
                if avg > 0 and current > avg * settings.SPREAD_ANOMALY_MULTIPLIER:
                    anomalies.append({
                        "exchange": exchange,
                        "symbol": symbol,
                        "current_spread_pct": round(current, 4),
                        "avg_spread_pct": round(avg, 4),
                        "multiplier": round(current / avg, 2),
                    })

    for a in anomalies:
        desc = (
            f"{a['exchange'].upper()} {a['symbol']} spread {a['current_spread_pct']:.3f}% "
            f"({a['multiplier']}× above average {a['avg_spread_pct']:.3f}%)"
        )
        await store.add_anomaly(
            type_="spread_anomaly",
            severity="high" if a["multiplier"] > 3 else "medium",
            description=desc,
            data=a
        )
        logger.warning(f"SPREAD ANOMALY: {desc}")

    return anomalies


async def detect_arbitrage_signals():
    """Detect price divergence > 0.2% between any pair of exchanges."""
    signals = []
    async with store._lock:
        prices = {}
        for exchange, symbols in store.exchange_prices.items():
            btc = symbols.get("BTC/USDT")
            if btc:
                prices[exchange] = (btc["bid"] + btc["ask"]) / 2  # mid price

    exchanges = list(prices.keys())
    for i in range(len(exchanges)):
        for j in range(i + 1, len(exchanges)):
            ex_a, ex_b = exchanges[i], exchanges[j]
            p_a, p_b = prices[ex_a], prices[ex_b]
            if p_a == 0 or p_b == 0:
                continue
            divergence_pct = abs(p_a - p_b) / min(p_a, p_b) * 100
            if divergence_pct >= 0.2:
                high_ex = ex_a if p_a > p_b else ex_b
                low_ex  = ex_b if p_a > p_b else ex_a
                high_p  = max(p_a, p_b)
                low_p   = min(p_a, p_b)
                signals.append({
                    "buy_exchange": low_ex,
                    "sell_exchange": high_ex,
                    "buy_price": round(low_p, 2),
                    "sell_price": round(high_p, 2),
                    "divergence_pct": round(divergence_pct, 4),
                    "arb_per_btc": round(high_p - low_p, 2),
                })

    for s in signals:
        desc = (
            f"ARB: Buy {s['buy_exchange'].upper()} ${s['buy_price']:,.2f} → "
            f"Sell {s['sell_exchange'].upper()} ${s['sell_price']:,.2f} "
            f"(+{s['divergence_pct']:.3f}% / ${s['arb_per_btc']:.2f}/BTC)"
        )
        await store.add_anomaly(
            type_="arbitrage",
            severity="high" if s["divergence_pct"] > 0.5 else "medium",
            description=desc,
            data=s
        )
        logger.warning(f"ARB SIGNAL: {desc}")

    return signals


async def detect_sentiment_shifts():
    """Flag if sentiment moved ±15 points across last 5 readings."""
    shifts = []
    async with store._lock:
        for key, history in store.sentiment_history.items():
            hist = list(history)
            if len(hist) < 5:
                continue
            recent = [h["score"] for h in hist[-5:]]
            shift = recent[-1] - recent[0]
            if abs(shift) >= settings.SENTIMENT_SHIFT_THRESHOLD:
                platform, symbol = key.split("_", 1)
                shifts.append({
                    "platform": platform,
                    "symbol": symbol,
                    "shift": round(shift, 1),
                    "from_score": round(recent[0], 1),
                    "to_score": round(recent[-1], 1),
                })

    for s in shifts:
        direction = "↑ BULLISH SURGE" if s["shift"] > 0 else "↓ BEARISH CRASH"
        desc = (
            f"SENTIMENT {direction}: {s['platform'].upper()} {s['symbol']} "
            f"moved {s['from_score']} → {s['to_score']} ({s['shift']:+.1f} pts)"
        )
        await store.add_anomaly(
            type_="sentiment_shift",
            severity="medium",
            description=desc,
            data=s
        )
        logger.warning(f"SENTIMENT SHIFT: {desc}")

    return shifts


async def detect_filing_spikes():
    """Flag if >5 filings from one regulator appear within the last hour."""
    spikes = []
    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    async with store._lock:
        filings = store.regulatory_filings
        by_source: dict[str, int] = {}
        for f in filings:
            if f["ts"] >= one_hour_ago:
                by_source[f["source"]] = by_source.get(f["source"], 0) + 1

    for source, count in by_source.items():
        if count >= settings.FILING_SPIKE_COUNT:
            spikes.append({"source": source, "count": count})
            desc = f"FILING SPIKE: {source} — {count} filings in last hour (threshold: {settings.FILING_SPIKE_COUNT})"
            await store.add_anomaly(
                type_="filing_spike",
                severity="high",
                description=desc,
                data={"source": source, "count": count}
            )
            logger.warning(f"FILING SPIKE: {desc}")

    return spikes


async def run_all_detection() -> dict:
    """Run all anomaly detectors and return summary."""
    spread  = await detect_spread_anomalies()
    arb     = await detect_arbitrage_signals()
    sent    = await detect_sentiment_shifts()
    filings = await detect_filing_spikes()

    summary = {
        "spread_anomalies": len(spread),
        "arbitrage_signals": len(arb),
        "sentiment_shifts": len(sent),
        "filing_spikes": len(filings),
        "total": len(spread) + len(arb) + len(sent) + len(filings)
    }
    if summary["total"] > 0:
        logger.info(f"Anomaly detection: {summary}")
    return summary
