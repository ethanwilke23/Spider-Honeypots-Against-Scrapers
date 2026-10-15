"""
Synthetic human-behaviour baseline.

A scripted browser session that behaves like a person reading the site: it
starts on the home page, only follows links that are visible on screen, pauses
on each page for a varying time, sometimes goes back, and stops after a varying
number of pages. It does not read robots.txt, JSON-LD or HTML comments.

It exists to measure the false-positive rate: if ordinary browsing ever reaches
a honeypot, that honeypot would also catch real visitors.

The literature supports the pattern, not the numbers. Tanaka et al. [11] and
Scripcariu et al. [25] describe human traffic as varied in timing and
navigation, unlike the rigid paths of simple bots. The parameter values in
HumanProfile are therefore chosen, not measured, and are stated as such in the
write-up. Every random choice comes from one seeded generator, so a session can
be repeated exactly from its seed.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from agents.playwright_baseline.crawler import SESSION_COOKIE_NAME, normalize_link

# Selects links a person could see and read: non-empty box, not hidden, with text.
VISIBLE_LINKS_JS = """
els => els.filter(e => {
  const r = e.getBoundingClientRect();
  const s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
         && parseFloat(s.opacity) > 0 && e.textContent.trim().length > 0;
}).map(e => e.getAttribute('href'))
"""


@dataclass(frozen=True)
class HumanProfile:
    pages_min: int = 3
    pages_max: int = 10
    dwell_median_seconds: float = 5.0
    dwell_sigma: float = 0.6  # spread of the log-normal dwell time
    dwell_min_seconds: float = 1.0
    dwell_max_seconds: float = 40.0
    back_probability: float = 0.15
    unvisited_weight: float = 3.0  # an unseen link is this many times likelier to be clicked


@dataclass
class PageView:
    path: str
    via: str  # "start", "link" or "back"
    status: int | None
    dwell_seconds: float
    visible_links: int


@dataclass
class SessionResult:
    base_url: str
    seed: int
    time_scale: float
    profile: dict
    session_id: str | None
    target_pages: int
    views: list[PageView] = field(default_factory=list)


# Random choices (no browser, so they can be unit-tested)

def sample_target_pages(rng: random.Random, profile: HumanProfile) -> int:
    return rng.randint(profile.pages_min, profile.pages_max)


def sample_dwell(rng: random.Random, profile: HumanProfile) -> float:
    value = rng.lognormvariate(math.log(profile.dwell_median_seconds), profile.dwell_sigma)
    return min(max(value, profile.dwell_min_seconds), profile.dwell_max_seconds)


def choose_link(rng: random.Random, candidates: list[str], visited: set[str], current: str, profile: HumanProfile) -> str | None:
    """Pick the next path to click from the visible links, or None if there is nothing new to click."""
    options = sorted({c for c in candidates if c != current})
    if not options:
        return None
    weights = [1.0 if path in visited else profile.unvisited_weight for path in options]
    return rng.choices(options, weights=weights, k=1)[0]


def decide_back(rng: random.Random, profile: HumanProfile, history_length: int) -> bool:
    return history_length > 1 and rng.random() < profile.back_probability


# The browser session

def run_session(
    base_url: str,
    seed: int,
    time_scale: float = 1.0,
    profile: HumanProfile = HumanProfile(),
    headless: bool = True,
) -> SessionResult:
    from playwright.sync_api import sync_playwright

    rng = random.Random(seed)
    result = SessionResult(
        base_url=base_url,
        seed=seed,
        time_scale=time_scale,
        profile=asdict(profile),
        session_id=None,
        target_pages=sample_target_pages(rng, profile),
    )
    visited: set[str] = set()
    history: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        response = page.goto(base_url + "/", wait_until="domcontentloaded")
        via, status = "start", response.status if response else None

        while True:
            path = urlparse(page.url).path or "/"
            visited.add(path)
            if via != "back":
                history.append(path)
            hrefs = page.eval_on_selector_all("a[href]", VISIBLE_LINKS_JS)
            links = [n for n in (normalize_link(base_url, h) for h in hrefs) if n]
            dwell = sample_dwell(rng, profile)
            result.views.append(PageView(path=path, via=via, status=status, dwell_seconds=round(dwell, 2), visible_links=len(set(links))))
            time.sleep(dwell * time_scale)

            if len(result.views) >= result.target_pages:
                break

            if decide_back(rng, profile, len(history)):
                history.pop()
                response = page.go_back(wait_until="domcontentloaded")
                via, status = "back", response.status if response else None
                continue

            target = choose_link(rng, links, visited, path, profile)
            if target is None:
                break
            locator = page.locator(f'a[href="{target}"]:visible').first
            with page.expect_navigation(wait_until="domcontentloaded") as navigation:
                locator.click()
            via, status = "link", navigation.value.status if navigation.value else None

        cookies = context.cookies()
        result.session_id = next((c["value"] for c in cookies if c["name"] == SESSION_COOKIE_NAME), None)
        browser.close()

    return result