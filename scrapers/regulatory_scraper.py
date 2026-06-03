"""
Regulatory filing scraper for SEC, MAS (Singapore), and OJK (Indonesia).

- SEC EDGAR: structured XML feed — Web Unlocker sufficient.
- MAS: React SPA — uses Bright Data Scraping Browser (JS render).
- OJK: Standard HTML — Web Unlocker with BeautifulSoup parsing.

All raw text is pushed to the signal store and queued for RAG ingestion.
"""
import json
import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.brightdata_client import bd_client
from data.store import store

logger = logging.getLogger(__name__)

# ── SEC EDGAR ──────────────────────────────────────────────────────────────────
SEC_RSS = "https://efts.sec.gov/LATEST/search-index?q=%22cryptocurrency%22+%22digital+asset%22&dateRange=custom&startdt={date}&forms=8-K,S-1,10-K"
SEC_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index?q=%22crypto%22&forms=8-K&dateRange=custom&startdt={date}&_source=file_date,period_of_report,entity_name,file_num,period_of_report,biz_location,inc_states,form_type&hits.hits._source=period_of_report,entity_name,file_date,form_type,file_num&hits.hits.total=true&hits.hits.highlight=true"

async def scrape_sec():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22cryptocurrency%22+%22digital+asset%22&forms=8-K,S-1&dateRange=custom&startdt={today}&hits.hits.total=true&hits.hits._source=period_of_report,entity_name,file_date,form_type,file_num"

    raw = await bd_client.unlocker_fetch(url)
    if not raw:
        return 0
    try:
        data = json.loads(raw)
        hits = data.get("hits", {}).get("hits", [])
        count = 0
        for hit in hits[:10]:
            src = hit.get("_source", {})
            title = f"{src.get('form_type','Filing')} — {src.get('entity_name','Unknown')}"
            file_num = src.get("file_num", "")
            url_filing = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={file_num}&type=&dateb=&owner=include&count=10"
            summary = (
                f"SEC {src.get('form_type')} filing by {src.get('entity_name')}. "
                f"Filed: {src.get('file_date','N/A')}. Period: {src.get('period_of_report','N/A')}."
            )
            await store.add_filing("SEC", title, url_filing, summary)
            count += 1
        logger.info(f"SEC: ingested {count} filings")
        return count
    except Exception as e:
        logger.warning(f"SEC parse error: {e}")
        return 0

# ── MAS (Monetary Authority of Singapore) ────────────────────────────────────
MAS_URL = "https://www.mas.gov.sg/news/media-releases"
# MAS uses a React SPA — we use Bright Data Web Unlocker with JS rendering

async def scrape_mas():
    raw = await bd_client.unlocker_fetch(MAS_URL, render_js=True)
    if not raw:
        return 0
    try:
        soup = BeautifulSoup(raw, "lxml")
        articles = soup.select("article, .media-release-item, [class*='release'], li.news-item")
        if not articles:
            # Fallback: grab any links containing "digital" or "payment" or "crypto"
            links = soup.find_all("a", href=True)
            articles = [
                a for a in links
                if any(kw in (a.get_text() + a["href"]).lower()
                       for kw in ["digital", "payment", "crypto", "token", "blockchain"])
            ]

        count = 0
        for a in articles[:8]:
            text = a.get_text(strip=True) if hasattr(a, 'get_text') else str(a)
            href = a.get("href", "") if hasattr(a, 'get') else ""
            if not text or len(text) < 10:
                continue
            url = href if href.startswith("http") else f"https://www.mas.gov.sg{href}"
            summary = f"MAS media release: {text[:300]}"
            await store.add_filing("MAS", text[:120], url, summary)
            count += 1
        logger.info(f"MAS: ingested {count} items")
        return count
    except Exception as e:
        logger.warning(f"MAS parse error: {e}")
        return 0

# ── OJK (Otoritas Jasa Keuangan — Indonesia) ─────────────────────────────────
OJK_URL = "https://ojk.go.id/en/berita-dan-kegiatan/siaran-pers/Pages/Default.aspx"

async def scrape_ojk():
    raw = await bd_client.unlocker_fetch(OJK_URL)
    if not raw:
        return 0
    try:
        soup = BeautifulSoup(raw, "lxml")
        # OJK uses SharePoint-style lists
        items = soup.select(".ms-rtestate-field a, .dfwp-item a, td a")
        count = 0
        for a in items[:10]:
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if not text or len(text) < 15:
                continue
            if not any(kw in text.lower() for kw in ["kripto", "crypto", "aset digital", "digital asset", "fintech", "payment"]):
                continue
            url = href if href.startswith("http") else f"https://ojk.go.id{href}"
            summary = f"OJK press release: {text[:300]}"
            await store.add_filing("OJK", text[:120], url, summary)
            count += 1
        logger.info(f"OJK: ingested {count} items")
        return count
    except Exception as e:
        logger.warning(f"OJK parse error: {e}")
        return 0

# ── Orchestrator ──────────────────────────────────────────────────────────────
async def scrape_all_regulatory():
    import asyncio
    results = await asyncio.gather(
        scrape_sec(), scrape_mas(), scrape_ojk(),
        return_exceptions=True
    )
    total = sum(r for r in results if isinstance(r, int))
    logger.info(f"Regulatory scrape complete: {total} total filings ingested")
    return total
