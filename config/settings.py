import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

class Settings:
    # ── Mode toggle ───────────────────────────────────────────────────────────
    # Set USE_BRIGHTDATA=true in .env to enable proxy (production)
    # Leave false to use direct fetch (testing/free mode)
    USE_BRIGHTDATA: bool = os.getenv("USE_BRIGHTDATA", "false").lower() == "true"

    # ── Bright Data ───────────────────────────────────────────────────────────
    BRIGHTDATA_API_KEY: str = os.getenv("BRIGHTDATA_API_KEY", "")
    BRIGHTDATA_WEB_UNLOCKER_ENDPOINT: str = os.getenv(
        "BRIGHTDATA_WEB_UNLOCKER_ENDPOINT",
        "https://api.brightdata.com/request"
    )
    BRIGHTDATA_SCRAPING_BROWSER_WS: str = os.getenv("BRIGHTDATA_SCRAPING_BROWSER_WS", "")
    BRIGHTDATA_SERP_API_ENDPOINT: str = os.getenv(
        "BRIGHTDATA_SERP_API_ENDPOINT",
        "https://api.brightdata.com/serp"
    )
    BRIGHTDATA_WEB_SCRAPER_DATASET_ID: str = os.getenv("BRIGHTDATA_WEB_SCRAPER_DATASET_ID", "")
    BRIGHTDATA_ZONE_UNLOCKER: str = os.getenv("BRIGHTDATA_ZONE_UNLOCKER", "unlocker")
    BRIGHTDATA_ZONE_SERP: str = os.getenv("BRIGHTDATA_ZONE_SERP", "serp")

    # ── AI ────────────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-70b-8192")

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ── App ───────────────────────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SCRAPE_INTERVAL_SECONDS: int = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "30"))
    SENTIMENT_INTERVAL_SECONDS: int = int(os.getenv("SENTIMENT_INTERVAL_SECONDS", "300"))
    REGULATORY_INTERVAL_SECONDS: int = int(os.getenv("REGULATORY_INTERVAL_SECONDS", "900"))
    JOBS_INTERVAL_SECONDS: int = int(os.getenv("JOBS_INTERVAL_SECONDS", "3600"))

    # ── Exchanges to monitor ──────────────────────────────────────────────────
    EXCHANGES = [
        "binance", "coinbase", "kraken", "okx", "bybit",
        "huobi", "gate", "kucoin", "bitfinex", "gemini"
    ]

    # ── Regulatory sources ────────────────────────────────────────────────────
    REGULATORY_SOURCES = {
        "SEC": "https://efts.sec.gov/LATEST/search-index?q=%22cryptocurrency%22&forms=8-K",
        "MAS": "https://www.mas.gov.sg/news/media-releases",
        "OJK": "https://ojk.go.id/en/berita-dan-kegiatan/siaran-pers/Pages/Default.aspx",
    }

    # ── Job signal companies ──────────────────────────────────────────────────
    JOB_COMPANIES = [
        "Coinbase", "Binance", "Kraken", "Ripple", "Chainalysis",
        "Fireblocks", "Anchorage", "Galaxy Digital", "Gemini", "BlockFi"
    ]

    # ── SERP keywords ─────────────────────────────────────────────────────────
    SERP_KEYWORDS = [
        "crypto regulation Singapore 2025",
        "MAS digital payment token policy",
        "SEC crypto enforcement action",
        "OJK cryptocurrency Indonesia",
        "bitcoin ETF regulatory update",
    ]

    # ── Anomaly thresholds ────────────────────────────────────────────────────
    SPREAD_ANOMALY_MULTIPLIER: float = 2.0
    SENTIMENT_SHIFT_THRESHOLD: float = 15.0
    FILING_SPIKE_COUNT: int = 5

settings = Settings()