"""
Sentiment scraper — Reddit public JSON API + X/Twitter search via Web Unlocker.

Reddit: uses public .json API (no auth required).
X: uses Bright Data Web Unlocker to fetch nitter.net (public Twitter mirror)
   or direct search results, bypassing anti-scraping measures.

Sentiment scoring: keyword-based (fast, no model needed for MVP).
Upgrade path: swap with a Groq-powered classification call per batch.
"""
import json
import logging
import re
from bs4 import BeautifulSoup
from scrapers.brightdata_client import bd_client
from data.store import store

logger = logging.getLogger(__name__)

# Simple keyword-based sentiment scorer
BULLISH_WORDS = {
    "moon", "pump", "bullish", "ath", "buy", "long", "rally", "surge",
    "breakout", "hodl", "accumulate", "undervalued", "bullrun", "rip",
    "green", "gains", "up", "soaring", "exploding", "potential"
}
BEARISH_WORDS = {
    "dump", "bearish", "sell", "short", "crash", "drop", "rekt", "rug",
    "scam", "dead", "overvalued", "bubble", "collapse", "fear", "red",
    "losing", "down", "falling", "bleed", "correction", "panic"
}

def score_text(text: str) -> float:
    """Returns sentiment score 0-100 (50 = neutral)."""
    text = text.lower()
    words = re.findall(r'\b\w+\b', text)
    bull = sum(1 for w in words if w in BULLISH_WORDS)
    bear = sum(1 for w in words if w in BEARISH_WORDS)
    total = bull + bear
    if total == 0:
        return 50.0
    return round((bull / total) * 100, 1)

# ── Reddit ────────────────────────────────────────────────────────────────────
REDDIT_SEARCHES = {
    "BTC":  "https://www.reddit.com/r/Bitcoin+CryptoCurrency/search.json?q=bitcoin+BTC&sort=new&limit=50&restrict_sr=1",
    "ETH":  "https://www.reddit.com/r/ethereum+CryptoCurrency/search.json?q=ethereum+ETH&sort=new&limit=50&restrict_sr=1",
    "SOL":  "https://www.reddit.com/r/solana+CryptoCurrency/search.json?q=solana+SOL&sort=new&limit=30&restrict_sr=1",
    "MKT":  "https://www.reddit.com/r/CryptoCurrency/search.json?q=crypto+market&sort=new&limit=50&restrict_sr=1",
}

async def scrape_reddit_sentiment():
    results = {}
    for symbol, url in REDDIT_SEARCHES.items():
        raw = await bd_client.unlocker_fetch(url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            posts = data.get("data", {}).get("children", [])
            texts = []
            for p in posts:
                post_data = p.get("data", {})
                texts.append(post_data.get("title", "") + " " + post_data.get("selftext", ""))

            combined = " ".join(texts)
            score = score_text(combined)
            mentions = len(posts)
            await store.update_sentiment("reddit", symbol, score, mentions)
            results[symbol] = {"score": score, "mentions": mentions}
            logger.debug(f"Reddit {symbol}: score={score}, mentions={mentions}")
        except Exception as e:
            logger.warning(f"Reddit sentiment parse error [{symbol}]: {e}")

    logger.info(f"Reddit sentiment scraped: {results}")
    return results

# ── X / Twitter (via Nitter mirror through Web Unlocker) ─────────────────────
NITTER_SEARCHES = {
    "BTC":  "https://nitter.net/search?f=tweets&q=%23Bitcoin+OR+%24BTC&since=1h",
    "ETH":  "https://nitter.net/search?f=tweets&q=%23Ethereum+OR+%24ETH&since=1h",
    "SOL":  "https://nitter.net/search?f=tweets&q=%23Solana+OR+%24SOL&since=1h",
    "REG":  "https://nitter.net/search?f=tweets&q=crypto+regulation+SEC+MAS+OJK&since=6h",
}

async def scrape_x_sentiment():
    results = {}
    for symbol, url in NITTER_SEARCHES.items():
        raw = await bd_client.unlocker_fetch(url, render_js=False)
        if not raw:
            continue
        try:
            soup = BeautifulSoup(raw, "lxml")
            tweets = soup.select(".tweet-content, .timeline-item .content")
            texts = [t.get_text(strip=True) for t in tweets]
            if not texts:
                # fallback: grab any paragraphs
                texts = [p.get_text(strip=True) for p in soup.find_all("p")]

            combined = " ".join(texts)
            score = score_text(combined)
            mentions = len(texts)
            await store.update_sentiment("x", symbol, score, mentions)
            results[symbol] = {"score": score, "mentions": mentions}
            logger.debug(f"X {symbol}: score={score}, mentions={mentions}")
        except Exception as e:
            logger.warning(f"X sentiment parse error [{symbol}]: {e}")

    logger.info(f"X sentiment scraped: {results}")
    return results

# ── Orchestrator ──────────────────────────────────────────────────────────────
async def scrape_all_sentiment():
    import asyncio
    reddit, x = await asyncio.gather(
        scrape_reddit_sentiment(),
        scrape_x_sentiment(),
        return_exceptions=True
    )
    return {"reddit": reddit, "x": x}
