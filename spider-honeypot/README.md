# Spider Honeypots Against LLM-Driven Scrapers

Research code for the COS 700 honours project (University of Pretoria).

Traditional spider honeypots were designed for scrapers that follow links
mechanically. LLM-driven agents read content, reason about whether a page is
worth visiting, and may interpret robots.txt rather than simply obey it. This
project builds a local, fully synthetic decoy website containing three honeypot
variants, and tests how different scrapers behave when they meet them.

> **Repository history note.** This repository was created on 14 October 2026,
> after the implementation of Phases 0 to 5 was already complete. Version
> control was not used during initial development. The earlier commits were
> created retrospectively, grouping the existing code by development phase in
> the order it was built. Their dates therefore show when the repository was
> created, not when the work was done, and intermediate commits are not
> guaranteed to run on their own. `PROGRESS.md` records the work by phase.
> History from this point on is real.

## What is being tested

The decoy site is a fictional company website, "Dunwoodie Data Analytics". It
hosts three honeypots:

| Variant | Path | How it is reached | What it tests |
|---|---|---|---|
| Semantic trap | `/internal/reports/q3-export-2026` | Only through JSON-LD data on the homepage | Whether an agent judges the page valuable enough to extract |
| Prompt-injection trap | `/documents/vendor-notes` | Through a blog link with no visible text | Whether an agent follows an instruction hidden in an HTML comment (a canary token) |
| Dynamic link-graph trap | `/archive/restricted/page/{n}` | Only mentioned as a Disallow entry in robots.txt | Whether an agent reasons about robots.txt and keeps following a chain of pages |

Three agents are run against it:

| Agent | Description |
|---|---|
| Playwright baseline | A mechanical crawler that follows links and obeys robots.txt. It is the control. |
| Crawl4AI | An open-source scraper using a local model served by Ollama (no API cost). |
| Claude computer use | Claude controlling a headless browser through screenshots. Built but not yet run, because it uses the paid API. |

Every request is logged to Postgres, so the server's logs are the ground truth
for which pages each agent visited.

## Stack

- Python 3.12 or newer, FastAPI
- Postgres through async SQLAlchemy (asyncpg driver)
- Playwright, Crawl4AI and Ollama for the agents
- pytest

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies and the browser used by the agents
pip install -r requirements.txt
playwright install chromium

# 3. Configure the environment
cp .env.example .env             # Windows: copy .env.example .env

# 4. Start Postgres with Docker, or use a native install
docker compose up -d
# Native install: create the user and database named in .env, for example
#   CREATE USER honeypot_user WITH PASSWORD 'honeypot_pass';
#   CREATE DATABASE spider_honeypot OWNER honeypot_user;

# 5. Run the tests (no database needed)
pytest -v

# 6. Start the site
uvicorn app.main:app --reload
```

With the server running, `http://127.0.0.1:8000/health` should return
`{"status":"ok","database":"reachable"}` and `http://127.0.0.1:8000/` shows the
decoy site.

## Running the agents

Start the server first. Run records are written to `agent_runs/`, which is not
committed.

```bash
# Playwright baseline
python -m agents.playwright_baseline.run

# Crawl4AI (Ollama must be running and the model pulled: ollama pull llama3.2)
crawl4ai-setup                   # once
python -m agents.crawl4ai_scraper.run --input-format markdown
python -m agents.crawl4ai_scraper.run --input-format html --max-pages 5

# Claude computer use: does nothing unless told to
python -m agents.claude_computer_use.run --env-check            # free browser check
python -m agents.claude_computer_use.run --confirm-spend        # paid; needs the anthropic
                                                                # package and ANTHROPIC_API_KEY
```

The Playwright and Claude runs record the `hp_session` cookie, so they can be
joined to the server logs by session id. Crawl4AI cannot read the cookie, so its
runs are matched to the logs by time window.

## Repository layout

```
app/
  config.py             Settings (environment variables or .env)
  db.py                 Async database engine and session
  main.py               FastAPI app: routes, middleware, table creation
  middleware.py         Logs every request and every honeypot hit
  models/               RequestLog and TrapHitEvent tables
  site/                 The legitimate decoy pages, robots.txt and sitemap
  honeypots/
    schemas.py          Design schemas for the three variants
    specs.py            The concrete specs
    validation.py       Checks that every failure mode is covered
    content.py          Synthetic page content (Faker)
    routes.py           The three honeypot routes and path helpers
agents/
  playwright_baseline/  Mechanical control crawler
  crawl4ai_scraper/     Crawl4AI harness using a local Ollama model
  claude_computer_use/  Claude computer-use harness (guarded against accidental spend)
tests/                  Unit tests
docker-compose.yml      Local Postgres
PROGRESS.md             Status by phase
```

## Status

Phases 0 to 5 are complete, except that the Claude computer-use agent has not yet
been run. The experiment itself (Phases 6 to 11) has not started. See
`PROGRESS.md` for details and known limitations.

## About the data

All page content, company names, figures and identifiers are synthetic. No real
organisation or person is referenced, and the contact address on the site uses
the reserved `.invalid` domain. The ethics documentation for the project is held
separately and is not part of this repository.