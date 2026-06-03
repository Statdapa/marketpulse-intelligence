"""
In-memory signal store — single source of truth for all scraped data.
In production, swap with Redis or TimescaleDB for persistence + history.
"""
import asyncio
from collections import deque
from datetime import datetime
from typing import Any

class SignalStore:
    def __init__(self):
        self._lock = asyncio.Lock()

        # Exchange pricing: {exchange: {symbol: {bid, ask, spread, spread_pct, ts}}}
        self.exchange_prices: dict[str, dict] = {}

        # Historical spread snapshots for anomaly detection (last 200 per exchange)
        self.spread_history: dict[str, deque] = {}

        # Regulatory filings: list of {source, title, url, summary, ts}
        self.regulatory_filings: list[dict] = []

        # Sentiment scores: {platform_symbol: {score, mention_count, ts}}
        self.sentiment: dict[str, dict] = {}

        # Sentiment history for shift detection (last 50 per key)
        self.sentiment_history: dict[str, deque] = {}

        # Job postings: list of {company, title, url, department, ts}
        self.job_postings: list[dict] = []

        # News items: list of {source, headline, url, summary, ts}
        self.news_items: list[dict] = []

        # Active anomalies: list of {type, severity, description, data, ts}
        self.anomalies: list[dict] = []

        # SERP results: list of {keyword, results, ts}
        self.serp_results: list[dict] = []

        # RAG document buffer — fed into ChromaDB
        self.rag_buffer: list[dict] = []

    async def update_price(self, exchange: str, symbol: str, bid: float, ask: float):
        async with self._lock:
            spread = ask - bid
            spread_pct = (spread / bid) * 100 if bid else 0
            if exchange not in self.exchange_prices:
                self.exchange_prices[exchange] = {}
            if exchange not in self.spread_history:
                self.spread_history[exchange] = deque(maxlen=200)

            self.exchange_prices[exchange][symbol] = {
                "bid": bid, "ask": ask,
                "spread": spread, "spread_pct": spread_pct,
                "ts": datetime.utcnow().isoformat()
            }
            self.spread_history[exchange].append({
                "spread_pct": spread_pct,
                "ts": datetime.utcnow().isoformat()
            })

    async def add_filing(self, source: str, title: str, url: str, summary: str):
        async with self._lock:
            self.regulatory_filings.insert(0, {
                "source": source, "title": title,
                "url": url, "summary": summary,
                "ts": datetime.utcnow().isoformat()
            })
            self.regulatory_filings = self.regulatory_filings[:200]
            self.rag_buffer.append({
                "type": "regulatory", "source": source,
                "content": f"{title}\n{summary}", "url": url,
                "ts": datetime.utcnow().isoformat()
            })

    async def update_sentiment(self, platform: str, symbol: str, score: float, mentions: int):
        async with self._lock:
            key = f"{platform}_{symbol}"
            if key not in self.sentiment_history:
                self.sentiment_history[key] = deque(maxlen=50)
            self.sentiment[key] = {
                "platform": platform, "symbol": symbol,
                "score": score, "mentions": mentions,
                "ts": datetime.utcnow().isoformat()
            }
            self.sentiment_history[key].append({
                "score": score, "ts": datetime.utcnow().isoformat()
            })

    async def add_job(self, company: str, title: str, url: str, department: str):
        async with self._lock:
            self.job_postings.insert(0, {
                "company": company, "title": title,
                "url": url, "department": department,
                "ts": datetime.utcnow().isoformat()
            })
            self.job_postings = self.job_postings[:500]

    async def add_news(self, source: str, headline: str, url: str, summary: str):
        async with self._lock:
            existing = [n["url"] for n in self.news_items]
            if url in existing:
                return
            self.news_items.insert(0, {
                "source": source, "headline": headline,
                "url": url, "summary": summary,
                "ts": datetime.utcnow().isoformat()
            })
            self.news_items = self.news_items[:300]
            self.rag_buffer.append({
                "type": "news", "source": source,
                "content": f"{headline}\n{summary}", "url": url,
                "ts": datetime.utcnow().isoformat()
            })

    async def add_anomaly(self, type_: str, severity: str, description: str, data: dict):
        async with self._lock:
            self.anomalies.insert(0, {
                "type": type_, "severity": severity,
                "description": description, "data": data,
                "ts": datetime.utcnow().isoformat()
            })
            self.anomalies = self.anomalies[:100]

    async def add_serp(self, keyword: str, results: list):
        async with self._lock:
            self.serp_results.insert(0, {
                "keyword": keyword, "results": results,
                "ts": datetime.utcnow().isoformat()
            })
            self.serp_results = self.serp_results[:200]
            for r in results[:3]:
                self.rag_buffer.append({
                    "type": "serp", "source": "google",
                    "content": f"{keyword}\n{r.get('title','')}\n{r.get('snippet','')}",
                    "url": r.get("url", ""),
                    "ts": datetime.utcnow().isoformat()
                })

    def drain_rag_buffer(self) -> list[dict]:
        buf = self.rag_buffer.copy()
        self.rag_buffer.clear()
        return buf

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for API responses."""
        return {
            "exchange_prices": self.exchange_prices,
            "regulatory_filings": self.regulatory_filings[:20],
            "sentiment": self.sentiment,
            "job_postings": self.job_postings[:50],
            "news_items": self.news_items[:30],
            "anomalies": self.anomalies[:20],
            "serp_results": self.serp_results[:10],
        }

# Global singleton
store = SignalStore()
