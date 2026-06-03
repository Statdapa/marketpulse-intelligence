"""
Bright Data unified client.
Wraps Web Unlocker, Scraping Browser, SERP API, and Web Scraper API.
All anti-bot bypassing happens here — callers just get clean HTML/JSON back.

Currently running in DIRECT mode (no Bright Data proxy).
To enable Bright Data: set BRIGHTDATA_API_KEY in .env and switch USE_BRIGHTDATA=true
"""
import asyncio
import logging
import aiohttp
from config.settings import settings

logger = logging.getLogger(__name__)


class BrightDataClient:
    """Async HTTP client — direct mode or Bright Data proxy mode."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    # ── Web Unlocker (or direct fetch) ───────────────────────────────────────
    async def unlocker_fetch(self, url: str, render_js: bool = False) -> str:
        """
        Fetch a URL — direct mode for testing, Bright Data mode for production.
        Switch by setting USE_BRIGHTDATA=true in .env
        """
        if settings.USE_BRIGHTDATA and settings.BRIGHTDATA_API_KEY:
            return await self._brightdata_fetch(url, render_js)
        else:
            return await self._direct_fetch(url)

    async def _direct_fetch(self, url: str) -> str:
        """Direct HTTP fetch — no proxy. Works for public exchange APIs."""
        session = await self._session_get()
        try:
            async with session.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as e:
            logger.warning(f"Direct fetch failed for {url}: {e}")
            return ""

    async def _brightdata_fetch(self, url: str, render_js: bool = False) -> str:
        """Fetch via Bright Data Web Unlocker — bypasses CAPTCHAs, IP bans."""
        session = await self._session_get()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.BRIGHTDATA_API_KEY}",
        }
        payload = {
            "zone": settings.BRIGHTDATA_ZONE_UNLOCKER,
            "url": url,
            "format": "raw",
            "render": render_js,
        }
        try:
            async with session.post(
                settings.BRIGHTDATA_WEB_UNLOCKER_ENDPOINT,
                json=payload, headers=headers
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as e:
            logger.warning(f"Web Unlocker failed for {url}: {e}")
            return ""

    # ── SERP API ──────────────────────────────────────────────────────────────
    async def serp_search(self, keyword: str, num_results: int = 10) -> list[dict]:
        """
        Google search via Bright Data SERP API.
        Falls back to empty list if not configured.
        """
        if not settings.USE_BRIGHTDATA or not settings.BRIGHTDATA_API_KEY:
            logger.debug(f"SERP API not configured — skipping '{keyword}'")
            return []

        session = await self._session_get()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.BRIGHTDATA_API_KEY}",
        }
        payload = {
            "zone": settings.BRIGHTDATA_ZONE_SERP,
            "query": keyword,
            "num": num_results,
            "country": "us",
            "output": "json",
        }
        try:
            async with session.post(
                settings.BRIGHTDATA_SERP_API_ENDPOINT,
                json=payload, headers=headers
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "position": item.get("position", 0),
                    }
                    for item in data.get("organic", [])
                ]
        except Exception as e:
            logger.warning(f"SERP API failed for '{keyword}': {e}")
            return []

    # ── Web Scraper API (Dataset) ─────────────────────────────────────────────
    async def dataset_trigger(self, dataset_id: str, inputs: list[dict]) -> str | None:
        """Trigger a Bright Data dataset scrape. Returns snapshot_id."""
        if not settings.USE_BRIGHTDATA or not settings.BRIGHTDATA_API_KEY:
            return None

        session = await self._session_get()
        headers = {
            "Authorization": f"Bearer {settings.BRIGHTDATA_API_KEY}",
            "Content-Type": "application/json",
        }
        url = f"https://api.brightdata.com/datasets/v3/trigger?dataset_id={dataset_id}&format=json"
        try:
            async with session.post(url, json=inputs, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("snapshot_id")
        except Exception as e:
            logger.warning(f"Dataset trigger failed: {e}")
            return None

    async def dataset_poll(self, snapshot_id: str, max_wait: int = 120) -> list[dict]:
        """Poll for dataset snapshot completion, return records."""
        session = await self._session_get()
        headers = {"Authorization": f"Bearer {settings.BRIGHTDATA_API_KEY}"}
        url = f"https://api.brightdata.com/datasets/v3/snapshot/{snapshot_id}?format=json"
        for _ in range(max_wait // 5):
            await asyncio.sleep(5)
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 202:
                        continue
            except Exception as e:
                logger.warning(f"Dataset poll error: {e}")
        logger.warning(f"Dataset poll timed out for snapshot {snapshot_id}")
        return []

    def scraping_browser_ws_url(self) -> str:
        """WebSocket endpoint for Playwright Scraping Browser."""
        return settings.BRIGHTDATA_SCRAPING_BROWSER_WS

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Global singleton
bd_client = BrightDataClient()