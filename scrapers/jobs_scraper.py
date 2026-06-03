"""
Job signal scraper — uses Bright Data Web Scraper API (Dataset triggers)
for structured extraction from job boards.

Why job postings matter for market intelligence:
  - Compliance/risk hiring spike → upcoming regulatory response
  - Engineering hiring at exchange → new product/feature launch in ~6-8 weeks
  - AML/KYC specialist hiring → regulatory pressure signal
  - Layoffs → exchange financial stress signal

Sources: LinkedIn (via dataset), Greenhouse, Lever (company ATS pages).
"""
import logging
from bs4 import BeautifulSoup
from scrapers.brightdata_client import bd_client
from data.store import store
from config.settings import settings

logger = logging.getLogger(__name__)

# Bright Data pre-built LinkedIn dataset ID for job search
LINKEDIN_DATASET_ID = settings.BRIGHTDATA_WEB_SCRAPER_DATASET_ID

# Direct ATS pages for key crypto companies (Greenhouse / Lever)
# These are public pages — Web Unlocker handles any bot protection
COMPANY_ATS_PAGES = {
    "Coinbase":       "https://www.coinbase.com/careers/positions",
    "Binance":        "https://www.binance.com/en/careers/all-position",
    "Kraken":         "https://jobs.lever.co/kraken",
    "Ripple":         "https://ripple.com/company/careers/all-jobs/",
    "Chainalysis":    "https://www.chainalysis.com/careers/",
    "Fireblocks":     "https://www.fireblocks.com/company/careers/",
    "Anchorage":      "https://www.anchorage.com/company/careers",
    "Galaxy Digital": "https://boards.greenhouse.io/galaxydigital",
    "Gemini":         "https://www.gemini.com/careers",
}

# Signal-relevant job title keywords
HIGH_SIGNAL_TITLES = {
    "compliance", "aml", "kyc", "regulatory", "legal counsel",
    "risk", "policy", "government", "sanctions", "fraud",
    "blockchain engineer", "security engineer", "infrastructure",
    "product manager", "senior engineer"
}

def is_high_signal(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in HIGH_SIGNAL_TITLES)

def classify_department(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ["compliance", "aml", "kyc", "regulatory", "legal", "policy"]):
        return "Compliance & Legal"
    if any(w in t for w in ["engineer", "developer", "infrastructure", "security", "blockchain"]):
        return "Engineering"
    if any(w in t for w in ["risk", "fraud", "sanctions"]):
        return "Risk"
    if any(w in t for w in ["product", "design", "ux"]):
        return "Product"
    return "Other"

# ── LinkedIn via Bright Data Dataset API ─────────────────────────────────────
async def scrape_linkedin_jobs():
    """
    Trigger Bright Data's LinkedIn Jobs dataset for each company.
    Dataset handles login walls, pagination, and structured extraction.
    """
    if not LINKEDIN_DATASET_ID:
        logger.debug("No LinkedIn dataset ID configured — skipping")
        return []

    inputs = [
        {"keyword": f"{company} crypto", "location": "worldwide"}
        for company in settings.JOB_COMPANIES
    ]
    snapshot_id = await bd_client.dataset_trigger(LINKEDIN_DATASET_ID, inputs)
    if not snapshot_id:
        return []

    records = await bd_client.dataset_poll(snapshot_id)
    results = []
    for r in records:
        title = r.get("job_title", r.get("title", ""))
        company = r.get("company_name", r.get("company", ""))
        url = r.get("job_url", r.get("url", ""))
        if title and company:
            dept = classify_department(title)
            await store.add_job(company, title, url, dept)
            results.append({"company": company, "title": title, "dept": dept})
    logger.info(f"LinkedIn jobs: {len(results)} scraped")
    return results

# ── Direct ATS pages via Web Unlocker ────────────────────────────────────────
async def scrape_ats_page(company: str, url: str) -> list[dict]:
    raw = await bd_client.unlocker_fetch(url, render_js=True)
    if not raw:
        return []

    soup = BeautifulSoup(raw, "lxml")
    jobs = []

    # Generic selectors that work across Greenhouse, Lever, and custom pages
    selectors = [
        "a.posting-title", ".job-title a", "h3 a", ".opening a",
        "[data-qa='job-list-item'] a", ".careers-list-item a",
        "li.position a", ".position-title"
    ]

    for sel in selectors:
        items = soup.select(sel)
        if items:
            for item in items[:20]:
                title = item.get_text(strip=True)
                href = item.get("href", "")
                if title and len(title) > 5:
                    job_url = href if href.startswith("http") else f"{url.rstrip('/')}{href}"
                    dept = classify_department(title)
                    await store.add_job(company, title, job_url, dept)
                    jobs.append({"company": company, "title": title, "dept": dept})
            break  # stop at first successful selector

    logger.debug(f"{company} ATS: {len(jobs)} jobs found")
    return jobs

async def scrape_all_jobs():
    import asyncio
    tasks = [
        scrape_ats_page(company, url)
        for company, url in COMPANY_ATS_PAGES.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total = sum(len(r) for r in results if isinstance(r, list))

    # Also try LinkedIn dataset if configured
    linkedin = await scrape_linkedin_jobs()
    total += len(linkedin)

    logger.info(f"Job scrape complete: {total} postings collected")
    return total
