# MarketPulse Intelligence
### Enterprise Web Intelligence Platform — Track 2: Finance & Market Intelligence

Real-time crypto market intelligence powered by **Bright Data** + **Groq LLaMA3** + **LangChain RAG**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BRIGHT DATA LAYER                         │
│  Web Unlocker  │  Scraping Browser  │  SERP API  │  Dataset │
└────────┬───────────────────────────────────────────┬────────┘
         │                                           │
         ▼                                           ▼
┌─────────────────────┐              ┌──────────────────────────┐
│   SCRAPER LAYER     │              │   STRUCTURED DATASETS    │
│  exchange_scraper   │              │   jobs_scraper (LinkedIn) │
│  regulatory_scraper │              │   serp_monitor           │
│  sentiment_scraper  │              └──────────────────────────┘
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    SIGNAL STORE (in-memory)                  │
│  exchange_prices │ regulatory_filings │ sentiment            │
│  job_postings   │ news_items         │ anomalies            │
└────────┬───────────────────────┬─────────────────────────────┘
         │                       │
         ▼                       ▼
┌──────────────────┐    ┌──────────────────────────────────────┐
│ ANOMALY DETECTOR │    │          RAG PIPELINE                │
│  - Arb signals   │    │  ChromaDB ← scraped docs             │
│  - Spread spikes │    │  Groq LLaMA3-70b ← queries          │
│  - Sent. shifts  │    │  LangChain ← orchestration           │
│  - Filing spikes │    └──────────────────────────────────────┘
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    DELIVERY LAYER                            │
│   FastAPI REST API  │  Telegram Alerts  │  Web Dashboard     │
└─────────────────────────────────────────────────────────────┘
```

---

## Bright Data Integration

| Product | Usage |
|---------|-------|
| **Web Unlocker** | Exchange ticker APIs, regulatory site pages, Reddit JSON API, Nitter/X search — all IP-rotated and fingerprint-spoofed |
| **Scraping Browser** | JS-heavy SPA pages: MAS (React), OJK, Coinbase careers |
| **SERP API** | Regulatory keyword monitoring across Google: "MAS VASP enforcement", "SEC crypto action" |
| **Web Scraper API** | LinkedIn Jobs dataset for structured job posting extraction |
| **MCP Server** | Agentic workflow orchestration for multi-step research tasks |

---

## Quickstart

```bash
# 1. Clone and install
git clone <repo>
cd marketpulse
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Fill in: BRIGHTDATA_API_KEY, GROQ_API_KEY, TELEGRAM_BOT_TOKEN

# 3. Run
python main.py
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

---

## API Reference

### Live Exchange Data
```bash
GET  /api/v1/exchanges              # All exchange prices
GET  /api/v1/exchanges/best         # Best spread exchange
GET  /api/v1/arbitrage?min_divergence=0.2   # Active arb signals
```

### Intelligence Feeds
```bash
GET  /api/v1/regulatory?source=MAS  # Regulatory filings (SEC/MAS/OJK)
GET  /api/v1/sentiment?symbol=BTC   # Reddit + X sentiment
GET  /api/v1/jobs?department=Compliance  # Job posting signals
GET  /api/v1/anomalies              # All active anomaly alerts
GET  /api/v1/serp                   # SERP keyword monitoring
```

### AI Query (RAG)
```bash
POST /api/v1/query
{
  "question": "What regulatory changes in Singapore affect our crypto ops this week?"
}
# → Groq LLaMA3-70b answer grounded in scraped regulatory docs + live data
```

### System
```bash
GET  /api/v1/snapshot               # Full state snapshot
POST /api/v1/scrape/trigger         # Manual scrape: {"target": "all"}
GET  /api/v1/scheduler/status       # Background job status
```

---

## Scrape Schedule

| Source | Interval | Method |
|--------|----------|--------|
| Exchange prices (10 exchanges) | 30s | Web Unlocker |
| Sentiment (Reddit + X) | 5m | Web Unlocker |
| Regulatory (SEC/MAS/OJK) | 15m | Web Unlocker + Scraping Browser |
| Job postings | 1h | Web Scraper API + Web Unlocker |
| SERP keyword monitoring | 30m | SERP API |
| RAG vector ingest | 10m | ChromaDB flush |

---

## Anomaly Detection

| Signal | Trigger | Severity |
|--------|---------|----------|
| Arbitrage | Price divergence ≥ 0.2% between any 2 exchanges | Medium/High |
| Spread anomaly | Spread > 2× rolling 30-day average | Medium/High |
| Sentiment shift | ±15 points in last 5 readings (~25 min) | Medium |
| Filing spike | > 5 filings from one regulator in 1 hour | High |

All anomalies → Telegram alert + REST API + RAG context window.

---

## Project Structure

```
marketpulse/
├── main.py                     # Entry point
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py             # All config, loaded from .env
├── data/
│   └── store.py                # In-memory signal store (swap with Redis/TimescaleDB)
├── scrapers/
│   ├── brightdata_client.py    # Bright Data unified client
│   ├── exchange_scraper.py     # 10 exchange tickers via Web Unlocker
│   ├── regulatory_scraper.py   # SEC, MAS, OJK via Web Unlocker + Scraping Browser
│   ├── sentiment_scraper.py    # Reddit + X sentiment via Web Unlocker
│   ├── jobs_scraper.py         # Job postings via Web Scraper API + ATS pages
│   └── serp_monitor.py         # SERP API keyword monitoring
├── anomaly/
│   └── detector.py             # Spread, arb, sentiment, filing spike detection
├── rag/
│   └── pipeline.py             # LangChain + Groq + ChromaDB RAG
├── alerts/
│   └── telegram_bot.py         # Telegram push alerts with dedup
└── api/
    ├── routes.py               # FastAPI REST endpoints
    └── scheduler.py            # APScheduler background jobs
```
