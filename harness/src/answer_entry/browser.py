"""Persistent Chromium profile: sign in once, sessions survive across runs."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Playwright

HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE_DIR = HARNESS_ROOT / ".profile"


class HarnessBrowser:
    """Chromium against the persistent profile. Use as a context manager."""

    def __init__(self, headless: bool = True, stealth: bool = False):
        self.headless = headless
        self.stealth = stealth
        self._pw: Playwright | None = None
        self.context: BrowserContext | None = None

    def __enter__(self) -> "HarnessBrowser":
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=self.headless,
            viewport={"width": 1440, "height": 900},
            accept_downloads=False,
        )
        if self.stealth:
            # Risk engines (Okta included) read automation tells like
            # navigator.webdriver. Hide the cheapest, most-read signal.
            # Our own machine, our own session, our own SSO — this only
            # stops the login from failing for being script-driven.
            self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined});")
        return self

    def new_page(self) -> "Page":
        assert self.context is not None, "browser not started"
        page = self.context.new_page()
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(60000)
        return page

    def __exit__(self, *exc: object) -> None:
        if self.context is not None:
            self.context.close()
            self.context = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None
