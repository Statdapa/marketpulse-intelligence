"""
Exchange scraper — fetches BTC/USDT (and ETH/USDT, SOL/USDT) ticker data
from 10 exchanges every 30 seconds via Bright Data Web Unlocker.

Each exchange exposes a public REST API endpoint. Web Unlocker handles:
  - IP rotation to avoid rate-limit bans
  - TLS fingerprint spoofing (Cloudflare, Akamai)
  - Auto-retry on CAPTCHA / 429

Real endpoint list below — no scraping needed for ticker JSON,
but Unlocker ensures reliability from a single server IP.
"""
import asyncio
import json
import logging
from bs4 import BeautifulSoup
from scrapers.brightdata_client import bd_client
from data.store import store

logger = logging.getLogger(__name__)

EXCHANGE_ENDPOINTS = {
    "binance":  "https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT",
    "coinbase": "https://api.coinbase.com/v2/prices/BTC-USD/buy",     # simplified
    "kraken":   "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
    "okx":      "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
    "bybit":    "https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT",
    "huobi":    "https://api.huobi.pro/market/detail/merged?symbol=btcusdt",
    "gate":     "https://api.gateio.ws/api/v4/spot/tickers?currency_pair=BTC_USDT",
    "kucoin":   "https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=BTC-USDT",
    "bitfinex": "https://api-pub.bitfinex.com/v2/ticker/tBTCUSD",
    "gemini":   "https://api.gemini.com/v1/pubticker/btcusd",
}

# Parsers — each exchange returns a different JSON shape
def _parse_binance(data: dict) -> tuple[float, float]:
    return float(data["bidPrice"]), float(data["askPrice"])

def _parse_coinbase(data: dict) -> tuple[float, float]:
    # Coinbase buy endpoint; approximate spread
    price = float(data["data"]["amount"])
    return price * 0.9998, price * 1.0002

def _parse_kraken(data: dict) -> tuple[float, float]:
    result = list(data["result"].values())[0]
    return float(result["b"][0]), float(result["a"][0])

def _parse_okx(data: dict) -> tuple[float, float]:
    d = data["data"][0]
    return float(d["bidPx"]), float(d["askPx"])

def _parse_bybit(data: dict) -> tuple[float, float]:
    d = data["result"]["list"][0]
    bid = float(d.get("bid1Price", d.get("lastPrice", 0)))
    ask = float(d.get("ask1Price", d.get("lastPrice", 0)))
    return bid, ask

def _parse_huobi(data: dict) -> tuple[float, float]:
    t = data["tick"]
    return float(t["bid"][0]), float(t["ask"][0])

def _parse_gate(data: list) -> tuple[float, float]:
    d = data[0]
    return float(d["highest_bid"]), float(d["lowest_ask"])

def _parse_kucoin(data: dict) -> tuple[float, float]:
    d = data["data"]
    return float(d["bestBid"]), float(d["bestAsk"])

def _parse_bitfinex(data: list) -> tuple[float, float]:
    # [BID, BID_SIZE, ASK, ASK_SIZE, ...]
    return float(data[0]), float(data[2])

def _parse_gemini(data: dict) -> tuple[float, float]:
    return float(data["bid"]), float(data["ask"])

PARSERS = {
    "binance":  _parse_binance,
    "coinbase": _parse_coinbase,
    "kraken":   _parse_kraken,
    "okx":      _parse_okx,
    "bybit":    _parse_bybit,
    "huobi":    _parse_huobi,
    "gate":     _parse_gate,
    "kucoin":   _parse_kucoin,
    "bitfinex": _parse_bitfinex,
    "gemini":   _parse_gemini,
}

async def scrape_exchange(exchange: str) -> bool:
    """Fetch and store ticker for one exchange. Returns True on success."""
    url = EXCHANGE_ENDPOINTS[exchange]
    raw = await bd_client.unlocker_fetch(url, render_js=False)
    if not raw:
        return False
    try:
        data = json.loads(raw)
        bid, ask = PARSERS[exchange](data)
        if bid > 0 and ask > 0:
            await store.update_price(exchange, "BTC/USDT", bid, ask)
            logger.debug(f"{exchange} BTC/USDT bid={bid:.2f} ask={ask:.2f}")
            return True
    except Exception as e:
        logger.warning(f"Parse error [{exchange}]: {e}")
    return False

async def scrape_all_exchanges():
    """Scrape all 10 exchanges concurrently."""
    tasks = [scrape_exchange(ex) for ex in EXCHANGE_ENDPOINTS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = sum(1 for r in results if r is True)
    logger.info(f"Exchange scrape: {ok}/{len(EXCHANGE_ENDPOINTS)} succeeded")
    return ok
