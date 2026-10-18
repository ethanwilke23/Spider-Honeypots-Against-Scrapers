"""
A text view of a web browser, for a language model that reads pages instead of looking at them.

This is the second way of giving Claude a browser (the first is the screenshot-based
computer-use agent). The model is the same; what changes is how the page reaches it:
as the page's visible text, followed by a numbered list of its visible links with their
addresses. This is close to what many commercial browser agents receive (an
accessibility-style view of the page next to, or instead of, a screenshot).

What the view contains, and does not:
  - It contains everything a person could read on the page (text hidden with CSS is
    left out) and, for every visible link, the address it leads to.
  - It does not contain HTML comments, the JSON-LD block or the page source. An
    instruction placed only in an HTML comment is therefore not seen by this agent.

The browser is a headless Playwright page. Every request for another site is blocked, so
the agent can only reach the test site, as in the desktop environment. Navigation is done
with real clicks (so the page's own scripts report a real click) and by typing an address.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

SESSION_COOKIE_NAME = "hp_session"
MAX_TEXT_CHARS = 8000
MAX_LINKS = 60


@dataclass
class Link:
    number: int
    text: str
    href: str


def format_view(url: str, status: int | None, title: str, text: str, links: list[Link]) -> str:
    """The text the model receives for one page. A pure function, so it can be tested."""
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n[page text cut off]"
    lines = [f"URL: {url}", f"Status: {status if status is not None else 'unknown'}", f"Title: {title}", "", "Page text:", text, "", "Links:"]
    if links:
        lines += [f"[{link.number}] {link.text} -> {link.href}" for link in links[:MAX_LINKS]]
    else:
        lines.append("(no links)")
    return "\n".join(lines)


def same_site(url: str, base_url: str) -> bool:
    a, b = urlparse(url), urlparse(base_url)
    return (a.scheme, a.hostname, a.port or (443 if a.scheme == "https" else 80)) == (
        b.scheme, b.hostname, b.port or (443 if b.scheme == "https" else 80)
    )


class TextBrowser:
    """Opens pages and returns their text view. One instance is one browsing session."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.pages_viewed: list[str] = []
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._links: list[tuple[object, Link]] = []
        self._last_status: int | None = None

    async def start(self) -> str:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(viewport={"width": 1280, "height": 800})

        async def block_other_sites(route):
            if same_site(route.request.url, self.base_url):
                await route.continue_()
            else:
                await route.abort()

        await self._context.route("**/*", block_other_sites)
        self._page = await self._context.new_page()
        self._page.on("response", self._remember_status)
        return await self.open_url(self.base_url)

    def _remember_status(self, response) -> None:
        if response.request.resource_type == "document" and response.frame == self._page.main_frame:
            self._last_status = response.status

    async def close(self) -> None:
        for closer in (lambda: self._browser.close() if self._browser else None, lambda: self._playwright.stop() if self._playwright else None):
            try:
                result = closer()
                if result is not None:
                    await result
            except Exception:
                pass

    @property
    def current_url(self) -> str:
        return self._page.url if self._page else ""

    async def get_session_cookie(self) -> str | None:
        cookies = await self._context.cookies()
        return next((c["value"] for c in cookies if c["name"] == SESSION_COOKIE_NAME), None)

    async def _view(self) -> str:
        page = self._page
        self._links = []
        for handle in await page.query_selector_all("a[href]"):
            try:
                if not await handle.is_visible():
                    continue
                text = " ".join((await handle.inner_text()).split())
                href = await handle.get_attribute("href")
            except Exception:
                continue
            if not text or not href or href.startswith(("javascript:", "#")):
                continue
            link = Link(len(self._links) + 1, text, urljoin(page.url, href))
            self._links.append((handle, link))
        body = await page.inner_text("body")
        view = format_view(page.url, self._last_status, await page.title(), body, [link for _, link in self._links])
        self.pages_viewed.append(page.url)
        return view

    async def open_url(self, address: str) -> str:
        """Go to an address (a full URL, or a path on the same site)."""
        target = urljoin(self._page.url if self._page.url != "about:blank" else self.base_url, address)
        if not same_site(target, self.base_url):
            raise ValueError(f"Only pages on this website can be opened; {address!r} is somewhere else.")
        self._last_status = None
        try:
            await self._page.goto(target, wait_until="domcontentloaded")
        except Exception as exc:
            raise ValueError(f"The page could not be opened: {str(exc).splitlines()[0]}") from None
        return await self._view()

    async def open_link(self, number: int) -> str:
        """Click the numbered link on the current page."""
        if not (1 <= number <= len(self._links)):
            raise ValueError(f"There is no link number {number}; the page has links 1 to {len(self._links)}.")
        handle, _ = self._links[number - 1]
        self._last_status = None
        try:
            async with self._page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                await handle.click()
        except Exception as exc:
            if type(exc).__name__ == "TimeoutError":
                # The click did not lead to a new page (for example a link to the page already open).
                self._last_status = self._last_status or 200
                return await self._view()
            raise ValueError(f"The link could not be opened: {str(exc).splitlines()[0]}") from None
        return await self._view()

    async def go_back(self) -> str:
        self._last_status = None
        response = await self._page.go_back(wait_until="domcontentloaded")
        if response is None:
            raise ValueError("There is no earlier page to go back to.")
        return await self._view()