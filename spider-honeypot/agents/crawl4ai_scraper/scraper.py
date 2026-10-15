"""
Crawl4AI harness: an open-source, LLM-based scraper.

The language model is a local open-weight model served by Ollama, so no API
key or per-token cost is needed. That makes this agent free to run, in
contrast to the paid Claude computer-use agent.

The agent is given an information-seeking goal and uses the model in two ways:
  1. Link prioritisation: BestFirstCrawlingStrategy with a keyword scorer
     built from the task's keywords.
  2. Content extraction: LLMExtractionStrategy, where the model reads each
     page and extracts what matches the task.

Input format: the extraction step can read either the page's markdown (the
library default) or its raw HTML. Converting to markdown drops HTML
comments, and the prompt-injection trap hides its instruction in a comment,
so in markdown mode that trap cannot be seen at all. The two modes answer
different questions and both are run, saved to separate files:
  - markdown: how the scraper behaves in its default configuration.
  - html: whether the model itself follows the injected instruction.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig, LLMConfig
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
from crawl4ai.extraction_strategy import LLMExtractionStrategy

from agents.shared.task import TASK_KEYWORDS, get_task_instruction

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

# The task wording and link keywords are shared with the other agents (agents/shared/task.py).
DEFAULT_TASK_KEYWORDS = TASK_KEYWORDS
DEFAULT_TASK_INSTRUCTION = get_task_instruction("crawl4ai")


@dataclass
class PageResult:
    url: str
    success: bool
    status_code: int | None
    extracted_content: str | None
    error_message: str | None


@dataclass
class Crawl4AIResult:
    base_url: str
    task_instruction: str
    input_format: str
    pages: list[PageResult] = field(default_factory=list)


def _check_ollama_reachable(base_url: str) -> None:
    """Raise a clear error if Ollama is not running, instead of failing deep inside a crawl."""
    try:
        urllib.request.urlopen(base_url, timeout=2)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {base_url}. Make sure it is installed and "
            f"running (`ollama serve`, or open the Ollama app), and that you have "
            f"pulled the model you want to use (e.g. `ollama pull llama3.2`)."
        ) from exc


async def run_crawl(
    base_url: str,
    task_instruction: str = DEFAULT_TASK_INSTRUCTION,
    keywords: list[str] | None = None,
    model: str = "llama3.2",
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    input_format: str = "markdown",
    max_pages: int = 30,
    max_depth: int = 4,
) -> Crawl4AIResult:
    _check_ollama_reachable(ollama_base_url)

    keywords = keywords or DEFAULT_TASK_KEYWORDS

    scorer = KeywordRelevanceScorer(keywords=keywords, weight=0.7)
    deep_crawl_strategy = BestFirstCrawlingStrategy(
        max_depth=max_depth,
        max_pages=max_pages,
        url_scorer=scorer,
    )

    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(provider=f"ollama/{model}", api_token=None, base_url=ollama_base_url),
        instruction=task_instruction,
        input_format=input_format,
    )

    run_config = CrawlerRunConfig(
        deep_crawl_strategy=deep_crawl_strategy,
        extraction_strategy=extraction_strategy,
        cache_mode=CacheMode.BYPASS,  # always fetch from the live server
    )

    result = Crawl4AIResult(base_url=base_url, task_instruction=task_instruction, input_format=input_format)

    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        crawl_results = await crawler.arun(url=base_url, config=run_config)
        # arun() returns a list when a deep-crawl strategy is set, a single result otherwise.
        if not isinstance(crawl_results, list):
            crawl_results = [crawl_results]

        for r in crawl_results:
            result.pages.append(
                PageResult(
                    url=r.url,
                    success=r.success,
                    status_code=getattr(r, "status_code", None),
                    extracted_content=getattr(r, "extracted_content", None),
                    error_message=getattr(r, "error_message", None),
                )
            )

    return result