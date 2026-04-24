from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from src.config import ScrapingConfig, SiteConfig


class ScraperStrategy(ABC):
    @abstractmethod
    async def fetch(self, url: str, site_config: SiteConfig, scraping_config: ScrapingConfig) -> str:
        """Fetch URL and return rendered HTML string."""

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""


class CrawleeStrategy(ScraperStrategy):
    def __init__(self) -> None:
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self, scraping_config: ScrapingConfig) -> None:
        if self._browser is not None:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=scraping_config.headless,
        )

    async def fetch(self, url: str, site_config: SiteConfig, scraping_config: ScrapingConfig) -> str:
        await self._ensure_browser(scraping_config)
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            html = await page.content()
            return html
        finally:
            await page.close()
            await context.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


class CamoufoxStrategy(ScraperStrategy):
    def __init__(self) -> None:
        self._browser = None

    async def _ensure_browser(self, scraping_config: ScrapingConfig) -> None:
        if self._browser is not None:
            return
        from camoufox.async_api import AsyncCamoufox
        self._camoufox = AsyncCamoufox(headless=scraping_config.headless)
        self._browser = await self._camoufox.__aenter__()

    async def fetch(self, url: str, site_config: SiteConfig, scraping_config: ScrapingConfig) -> str:
        await self._ensure_browser(scraping_config)
        page = await self._browser.new_page()
        try:
            # Inject cookies if the site config provides them
            if site_config.cookies:
                cookie_list = [
                    {"name": c.name, "value": c.value, "domain": c.domain, "path": "/"}
                    for c in site_config.cookies
                ]
                await page.context.add_cookies(cookie_list)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            return html
        finally:
            await page.close()

    async def close(self) -> None:
        if hasattr(self, "_camoufox"):
            try:
                await self._camoufox.__aexit__(None, None, None)
            except Exception:
                pass
            del self._camoufox
            self._browser = None


class ZendriverStrategy(ScraperStrategy):
    def __init__(self) -> None:
        self._browser = None

    async def _ensure_browser(self, scraping_config: ScrapingConfig) -> None:
        if self._browser is not None:
            return
        import zendriver as zd
        self._browser = await zd.start(
            headless=scraping_config.headless,
        )

    async def fetch(self, url: str, site_config: SiteConfig, scraping_config: ScrapingConfig) -> str:
        await self._ensure_browser(scraping_config)
        tab = await self._browser.get(url)
        await asyncio.sleep(5)  # Allow Cloudflare challenge to resolve
        html = await tab.get_content()
        return html

    async def close(self) -> None:
        if self._browser:
            try:
                await self._browser.stop()
            except Exception:
                pass
            self._browser = None


STRATEGIES: dict[str, type[ScraperStrategy]] = {
    "crawlee": CrawleeStrategy,
    "camoufox": CamoufoxStrategy,
    "zendriver": ZendriverStrategy,
}
