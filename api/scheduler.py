"""
Background scheduler — APScheduler AsyncIO backend.

Job schedule (configurable via .env):
  Exchange prices    → every 30s  (SCRAPE_INTERVAL_SECONDS)
  Sentiment          → every 5m   (SENTIMENT_INTERVAL_SECONDS)
  Regulatory filings → every 15m  (REGULATORY_INTERVAL_SECONDS)
  Job postings       → every 1h   (JOBS_INTERVAL_SECONDS)
  SERP monitor       → every 30m  (fixed)
  Anomaly detection  → after every exchange scrape
  Telegram flush     → after every anomaly run
  RAG ingest         → every 10m  (fixed)
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config.settings import settings

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _job_exchanges():
    from scrapers.exchange_scraper import scrape_all_exchanges
    from anomaly.detector import run_all_detection
    from alerts.telegram_bot import flush_new_anomalies
    await scrape_all_exchanges()
    await run_all_detection()
    await flush_new_anomalies()


async def _job_sentiment():
    from scrapers.sentiment_scraper import scrape_all_sentiment
    await scrape_all_sentiment()


async def _job_regulatory():
    from scrapers.regulatory_scraper import scrape_all_regulatory
    await scrape_all_regulatory()


async def _job_jobs():
    from scrapers.jobs_scraper import scrape_all_jobs
    await scrape_all_jobs()


async def _job_serp():
    from scrapers.serp_monitor import run_serp_monitor
    await run_serp_monitor()


async def _job_rag_ingest():
    from rag.pipeline import rag
    count = rag.flush_rag_buffer()
    if count:
        logger.info(f"RAG: flushed {count} documents to vector store")


def start_scheduler():
    scheduler.add_job(
        _job_exchanges,
        trigger=IntervalTrigger(seconds=settings.SCRAPE_INTERVAL_SECONDS),
        id="exchanges", name="Exchange Scraper", replace_existing=True
    )
    scheduler.add_job(
        _job_sentiment,
        trigger=IntervalTrigger(seconds=settings.SENTIMENT_INTERVAL_SECONDS),
        id="sentiment", name="Sentiment Scraper", replace_existing=True
    )
    scheduler.add_job(
        _job_regulatory,
        trigger=IntervalTrigger(seconds=settings.REGULATORY_INTERVAL_SECONDS),
        id="regulatory", name="Regulatory Scraper", replace_existing=True
    )
    scheduler.add_job(
        _job_jobs,
        trigger=IntervalTrigger(seconds=settings.JOBS_INTERVAL_SECONDS),
        id="jobs", name="Job Scraper", replace_existing=True
    )
    scheduler.add_job(
        _job_serp,
        trigger=IntervalTrigger(seconds=1800),  # 30 min
        id="serp", name="SERP Monitor", replace_existing=True
    )
    scheduler.add_job(
        _job_rag_ingest,
        trigger=IntervalTrigger(seconds=600),  # 10 min
        id="rag_ingest", name="RAG Ingest", replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started with jobs: exchanges, sentiment, regulatory, jobs, serp, rag_ingest")


def stop_scheduler():
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
