"""
MarketPulse Intelligence — FastAPI REST API

Endpoints:
  GET  /                          Health check + system status
  GET  /api/v1/snapshot           Full intelligence snapshot
  GET  /api/v1/exchanges          Live exchange prices & spreads
  GET  /api/v1/exchanges/best     Best spread for a symbol
  GET  /api/v1/arbitrage          Active arbitrage signals
  GET  /api/v1/regulatory         Recent regulatory filings
  GET  /api/v1/sentiment          Current sentiment scores
  GET  /api/v1/jobs               Job posting signals
  GET  /api/v1/news               Recent news items
  GET  /api/v1/anomalies          Active anomaly alerts
  GET  /api/v1/serp               SERP monitoring results
  POST /api/v1/query              Natural language AI query (RAG)
  POST /api/v1/scrape/trigger     Manually trigger a scrape cycle
  GET  /api/v1/scheduler/status   Scheduler job status
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import logging
import os

from data.store import store
from config.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="MarketPulse Intelligence API",
    description="Enterprise crypto market intelligence — powered by Bright Data + Groq",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ───────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    max_sources: Optional[int] = 5


class ScrapeRequest(BaseModel):
    target: str  # "exchanges" | "regulatory" | "sentiment" | "jobs" | "serp" | "all"


# ── Startup / shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    from api.scheduler import start_scheduler
    from alerts.telegram_bot import send_startup_message
    from rag.pipeline import rag
    rag.initialize()
    start_scheduler()
    await send_startup_message()
    logger.info("MarketPulse Intelligence API started")


@app.on_event("shutdown")
async def shutdown():
    from api.scheduler import stop_scheduler
    from scrapers.brightdata_client import bd_client
    stop_scheduler()
    await bd_client.close()
    logger.info("MarketPulse Intelligence API stopped")


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    """Serve the MarketPulse Intelligence dashboard."""
    dashboard_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    raise HTTPException(404, "Dashboard file not found")

@app.get("/")
async def health():
    snap = store.snapshot()
    return {
        "status": "operational",
        "version": "2.1.0",
        "exchanges_live": len(snap["exchange_prices"]),
        "anomalies_active": len(snap["anomalies"]),
        "filings_tracked": len(snap["regulatory_filings"]),
        "data_sources": {
            "bright_data_unlocker": bool(settings.BRIGHTDATA_API_KEY),
            "groq_rag": bool(settings.GROQ_API_KEY),
            "telegram_alerts": bool(settings.TELEGRAM_BOT_TOKEN),
        }
    }


# ── Intelligence snapshot ─────────────────────────────────────────────────────

@app.get("/api/v1/snapshot")
async def get_snapshot():
    """Full intelligence snapshot — all data sources combined."""
    return store.snapshot()


# ── Exchanges ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/exchanges")
async def get_exchanges(symbol: str = "BTC/USDT"):
    """Live prices and spreads across all monitored exchanges."""
    result = {}
    for exchange, symbols in store.exchange_prices.items():
        if symbol in symbols:
            result[exchange] = symbols[symbol]
    if not result:
        return {"message": "No data yet — scrape cycle in progress", "exchanges": {}}
    return {"symbol": symbol, "exchanges": result, "count": len(result)}


@app.get("/api/v1/exchanges/best")
async def get_best_spread(symbol: str = "BTC/USDT"):
    """Return the exchange with the tightest spread for a symbol."""
    best_exchange = None
    best_spread = float("inf")
    for exchange, symbols in store.exchange_prices.items():
        tick = symbols.get(symbol)
        if tick and tick["spread_pct"] < best_spread:
            best_spread = tick["spread_pct"]
            best_exchange = exchange
    if not best_exchange:
        raise HTTPException(404, "No price data available")
    return {
        "symbol": symbol,
        "best_exchange": best_exchange,
        "data": store.exchange_prices[best_exchange][symbol]
    }


# ── Arbitrage ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/arbitrage")
async def get_arbitrage(min_divergence: float = 0.1):
    """Active arbitrage signals above minimum divergence threshold."""
    arb_anomalies = [
        a for a in store.anomalies
        if a["type"] == "arbitrage"
        and a["data"].get("divergence_pct", 0) >= min_divergence
    ]
    return {
        "signals": arb_anomalies,
        "count": len(arb_anomalies),
        "threshold_pct": min_divergence
    }


# ── Regulatory ────────────────────────────────────────────────────────────────

@app.get("/api/v1/regulatory")
async def get_regulatory(source: Optional[str] = None, limit: int = 50):
    """Recent regulatory filings. Filter by source: SEC, MAS, OJK."""
    filings = store.regulatory_filings
    if source:
        filings = [f for f in filings if f["source"].upper() == source.upper()]
    return {
        "filings": filings[:limit],
        "count": len(filings),
        "sources": list({f["source"] for f in store.regulatory_filings})
    }


# ── Sentiment ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/sentiment")
async def get_sentiment(platform: Optional[str] = None, symbol: Optional[str] = None):
    """Current sentiment scores. Filter by platform (reddit/x) or symbol."""
    sentiment = store.sentiment
    if platform:
        sentiment = {k: v for k, v in sentiment.items() if k.startswith(platform.lower())}
    if symbol:
        sentiment = {k: v for k, v in sentiment.items() if symbol.upper() in k.upper()}
    return {"sentiment": sentiment, "count": len(sentiment)}


# ── Job signals ───────────────────────────────────────────────────────────────

@app.get("/api/v1/jobs")
async def get_jobs(
    company: Optional[str] = None,
    department: Optional[str] = None,
    limit: int = 100
):
    """Job posting signals. Filter by company or department."""
    jobs = store.job_postings
    if company:
        jobs = [j for j in jobs if company.lower() in j["company"].lower()]
    if department:
        jobs = [j for j in jobs if department.lower() in j["department"].lower()]
    # Compliance/risk jobs are highest signal — sort to top
    jobs = sorted(jobs, key=lambda j: 0 if "Compliance" in j.get("department","") else 1)
    return {"jobs": jobs[:limit], "count": len(store.job_postings)}


# ── News ──────────────────────────────────────────────────────────────────────

@app.get("/api/v1/news")
async def get_news(limit: int = 50):
    """Recent news items from all monitored sources."""
    return {"news": store.news_items[:limit], "count": len(store.news_items)}


# ── Anomalies ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/anomalies")
async def get_anomalies(type_filter: Optional[str] = None, severity: Optional[str] = None):
    """Active anomaly alerts. Filter by type or severity."""
    anomalies = store.anomalies
    if type_filter:
        anomalies = [a for a in anomalies if a["type"] == type_filter]
    if severity:
        anomalies = [a for a in anomalies if a["severity"] == severity.lower()]
    return {"anomalies": anomalies, "count": len(anomalies)}


# ── SERP ──────────────────────────────────────────────────────────────────────

@app.get("/api/v1/serp")
async def get_serp(keyword: Optional[str] = None):
    """SERP monitoring results. Filter by keyword."""
    results = store.serp_results
    if keyword:
        results = [r for r in results if keyword.lower() in r["keyword"].lower()]
    return {"results": results[:20], "count": len(results)}


# ── AI Query (RAG) ────────────────────────────────────────────────────────────

@app.post("/api/v1/query")
async def ai_query(req: QueryRequest):
    """
    Natural language query against the RAG intelligence layer.

    Examples:
      "What regulatory changes in Singapore affect our crypto ops this week?"
      "Which exchange has the best BTC spread right now?"
      "Are there any unusual arbitrage signals?"
      "What's the sentiment on Reddit about BTC today?"
    """
    from rag.pipeline import rag
    if not req.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    result = await rag.query(req.question)
    return result


# ── Manual scrape trigger ─────────────────────────────────────────────────────

@app.post("/api/v1/scrape/trigger")
async def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Manually trigger an immediate scrape cycle."""
    target = req.target.lower()
    job_map = {
        "exchanges":  "from scrapers.exchange_scraper import scrape_all_exchanges; import asyncio; asyncio.create_task(scrape_all_exchanges())",
        "regulatory": "from scrapers.regulatory_scraper import scrape_all_regulatory; import asyncio; asyncio.create_task(scrape_all_regulatory())",
        "sentiment":  "from scrapers.sentiment_scraper import scrape_all_sentiment; import asyncio; asyncio.create_task(scrape_all_sentiment())",
        "jobs":       "from scrapers.jobs_scraper import scrape_all_jobs; import asyncio; asyncio.create_task(scrape_all_jobs())",
        "serp":       "from scrapers.serp_monitor import run_serp_monitor; import asyncio; asyncio.create_task(run_serp_monitor())",
    }

    async def run_target(t: str):
        try:
            if t == "exchanges" or t == "all":
                from scrapers.exchange_scraper import scrape_all_exchanges
                await scrape_all_exchanges()
            if t == "regulatory" or t == "all":
                from scrapers.regulatory_scraper import scrape_all_regulatory
                await scrape_all_regulatory()
            if t == "sentiment" or t == "all":
                from scrapers.sentiment_scraper import scrape_all_sentiment
                await scrape_all_sentiment()
            if t == "jobs" or t == "all":
                from scrapers.jobs_scraper import scrape_all_jobs
                await scrape_all_jobs()
            if t == "serp" or t == "all":
                from scrapers.serp_monitor import run_serp_monitor
                await run_serp_monitor()
        except Exception as e:
            logger.error(f"Manual scrape error [{t}]: {e}")

    if target not in ("exchanges", "regulatory", "sentiment", "jobs", "serp", "all"):
        raise HTTPException(400, f"Unknown target: {target}. Use: exchanges, regulatory, sentiment, jobs, serp, all")

    background_tasks.add_task(run_target, target)
    return {"status": "triggered", "target": target, "message": f"Scrape job '{target}' started in background"}


# ── Scheduler status ──────────────────────────────────────────────────────────

@app.get("/api/v1/scheduler/status")
async def scheduler_status():
    """Return status of all background scheduler jobs."""
    from api.scheduler import scheduler
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })
    return {"jobs": jobs, "running": scheduler.running}
