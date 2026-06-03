"""
SERP API monitor — tracks regulatory and brand keywords across Google search.

Purpose: detect regulatory shifts BEFORE they appear in official filings.
A sudden spike in search results for "MAS VASP enforcement" or 
"SEC crypto lawsuit" is a leading signal worth alerting on.

Uses Bright Data SERP API to avoid IP bans and get clean structured results.
"""
import logging
from scrapers.brightdata_client import bd_client
from data.store import store
from config.settings import settings

logger = logging.getLogger(__name__)

async def run_serp_monitor():
    """Runs all configured keyword searches and stores results."""
    total = 0
    for keyword in settings.SERP_KEYWORDS:
        results = await bd_client.serp_search(keyword, num_results=10)
        if results:
            await store.add_serp(keyword, results)
            total += len(results)
            logger.debug(f"SERP '{keyword}': {len(results)} results")

    logger.info(f"SERP monitor complete: {total} results across {len(settings.SERP_KEYWORDS)} keywords")
    return total
