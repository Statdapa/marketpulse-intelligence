# MarketPulse Intelligence

A real-time crypto market intelligence platform that aggregates live data from eight exchanges, detects arbitrage and anomaly signals, monitors regulatory filings, and exposes a natural language query interface powered by Groq LLaMA3 over a RAG pipeline.

Built and submitted for the **Transforming Enterprise Through AI** hackathon on lablab.ai. An upgraded version was developed for the **Web Data UNLOCKED Hackathon**.

📄 [Full technical writeup on Medium](https://lnkd.in/gUsw2UGV)

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

## Features

- **Live Exchange Data** — simultaneous BTC/USDT bid-ask feeds from Binance, OKX, Kraken, Bybit, KuCoin, Huobi, Bitfinex, and Coinbase
- **Arbitrage Detection** — flags cross-exchange price divergence above a configurable threshold
- **Anomaly Detection** — monitors four signal types: spread anomaly, arbitrage, sentiment shift, and filing spike
- **Regulatory Monitor** — scrapes SEC EDGAR, MAS Singapore, and OJK Indonesia for new filings
- **Sentiment Scoring** — keyword-based bullish/bearish classification from Reddit and X
- **RAG Query Layer** — ask questions in plain English, get answers grounded in real-time market data via Groq LLaMA3-70b + ChromaDB
- **Telegram Alerts** — formatted notifications with deduplication
- **Interactive Dashboard** — live UI with auto-refresh every 30 seconds

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Background Jobs | APScheduler |
| Exchange Data | CCXT + direct API calls |
| Web Scraping | Bright Data Web Unlocker + aiohttp |
| AI Query Layer | LangChain + Groq LLaMA3-70b |
| Vector Store | ChromaDB |
| Alerts | Telegram Bot API |
| Frontend | Vanilla HTML/CSS/JS |

---

## Bright Data Integration

| Product | Usage |
|---|---|
| Web Unlocker | Exchange ticker APIs, regulatory site pages, Reddit JSON API, Nitter/X search — IP-rotated and fingerprint-spoofed |
| Scraping Browser | JS-heavy SPA pages: MAS (React), OJK, Coinbase careers |
| SERP API | Regulatory keyword monitoring: "MAS VASP enforcement", "SEC crypto action" |
| Web Scraper API | LinkedIn Jobs dataset for structured job posting extraction |

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Statdapa/marketpulse-intelligence.git
cd marketpulse-intelligence
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```
GROQ_API_KEY=your_groq_key_here
BRIGHTDATA_API_KEY=your_brightdata_key_here
TELEGRAM_BOT_TOKEN=your_telegram_token_here
USE_BRIGHTDATA=false
```

To get these keys:
- **Groq**: console.groq.com → API Keys (free)
- **Bright Data**: brightdata.com → free trial available
- **Telegram**: message @BotFather → /newbot

### 5. Run the server

```bash
python main.py
```

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8000/dashboard`

---

## API Reference

**Live Exchange Data**
```
GET  /api/v1/exchanges                          # All exchange prices
GET  /api/v1/exchanges/best                     # Best spread exchange
GET  /api/v1/arbitrage?min_divergence=0.2       # Active arbitrage signals
```

**Intelligence Feeds**
```
GET  /api/v1/regulatory?source=MAS              # Regulatory filings (SEC/MAS/OJK)
GET  /api/v1/sentiment?symbol=BTC               # Reddit + X sentiment
GET  /api/v1/anomalies                          # All active anomaly alerts
GET  /api/v1/serp                               # SERP keyword monitoring
```

**AI Query (RAG)**
```
POST /api/v1/query
{"question": "Which exchange has the tightest BTC spread right now?"}
```

Example response:
```json
{
  "answer": "Based on current data, Binance has the tightest BTC/USDT spread at 0.0013%, followed by Huobi at 0.0013% and OKX at 0.0130%. Coinbase currently shows the widest spread at 4.0%."
}
```

---

## Anomaly Detection

| Signal | Trigger | Severity |
|---|---|---|
| Arbitrage | Price divergence ≥ 0.2% between any 2 exchanges | Medium/High |
| Spread anomaly | Spread > 2× rolling 30-day average | Medium/High |
| Sentiment shift | ±15 points in last 5 readings (~25 min) | Medium |
| Filing spike | > 5 filings from one regulator in 1 hour | High |

All anomalies trigger a Telegram alert, REST API update, and RAG context window refresh.

---

## Scrape Schedule

| Source | Interval | Method |
|---|---|---|
| Exchange prices | 30s | Web Unlocker |
| Sentiment (Reddit + X) | 5m | Web Unlocker |
| Regulatory (SEC/MAS/OJK) | 15m | Web Unlocker + Scraping Browser |
| Job postings | 1h | Web Scraper API |
| SERP keyword monitoring | 30m | SERP API |
| RAG vector ingest | 10m | ChromaDB flush |

---

## Project Structure

```
marketpulse-intelligence/
├── main.py
├── requirements.txt
├── .env.example
├── dashboard.html
├── config/
│   └── settings.py
├── data/
│   └── store.py
├── scrapers/
│   ├── brightdata_client.py
│   ├── exchange_scraper.py
│   ├── regulatory_scraper.py
│   ├── sentiment_scraper.py
│   ├── jobs_scraper.py
│   └── serp_monitor.py
├── anomaly/
│   └── detector.py
├── rag/
│   └── pipeline.py
├── alerts/
│   └── telegram_bot.py
└── api/
    ├── routes.py
    └── scheduler.py
```

---

## Author

**Gilbert Geraldo Purba**
Statistics, Universitas Diponegoro
[LinkedIn](https://linkedin.com/in/gilbert-purba) · [Medium](https://medium.com/@91lbertjr)
