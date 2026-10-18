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
| Semantic trap | `/internal/reports/q3-export-2026` | A visible link in the first blog post ("Q3 financial export"), and JSON-LD data on the homepage | Whether an agent judges the page valuable enough to extract |
| Prompt-injection trap | `/documents/vendor-notes` | A visible link in the second blog post ("vendor notes") | Whether an agent follows an instruction to repeat a canary token, given once in an HTML comment and once in small visible text |
| Dynamic link-graph trap | `/archive/restricted/page/{n}` | A visible link on the blog index ("restricted archive"); the path is also a Disallow entry in robots.txt | Whether an agent keeps following a chain of pages, and whether it reasons about robots.txt |

The links are ordinary visible links, so an agent that works from screenshots can
see them. This also means an ordinary visitor might click them, which is what the
false-positive measurement is for. A link appears only while its variant is active.

Agents run against it:

| Agent | Description |
|---|---|
| Playwright baseline | A mechanical crawler that follows links and obeys robots.txt. It is the control. |
| Playwright, ignoring robots.txt | The same crawler with `--ignore-robots`: a traditional scraper that does not honour robots.txt, and the only mechanical agent that can reach the link-graph chain. |
| Crawl4AI | An open-source scraper using a local model served by Ollama (no API cost). |
| Claude computer use | Claude controlling a real browser window (tab bar and address bar) on a virtual screen inside Docker, through screenshots. Uses the paid API. |
| Claude text browser | The same Claude model reading each page as text plus a numbered list of links (no screenshots), in a headless browser on your computer. Differs from the line above only in perception. Uses the paid API. |

A scripted browser session is used to measure false positives. It browses like a
person would (visible links only, varied pauses and page counts, now and then
going back) and is not an agent under test.

Every request is logged to Postgres, so the server's logs are the ground truth
for which pages each agent visited. The pages also report DOM events (page views,
clicks, time on the page, scrolling, mouse and key activity) to `/_events`, stored
in the `client_event` table, so a page being viewed can be told apart from a page
being fetched. These beacon requests are not counted as page requests.

## Stack

- Python 3.12 or newer, FastAPI
- Postgres through async SQLAlchemy (asyncpg driver)
- Playwright, Crawl4AI and Ollama for the agents
- Docker (Desktop) for the Claude computer-use agent; Postgres can use it too
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

## Choosing which honeypot is active

The experiment tests each variant on its own, plus a control with no honeypots.
Set `HONEYPOT_VARIANT` (in `.env` or the environment) before starting the server:

| Value | Effect |
|---|---|
| `all` | All three honeypots (the default) |
| `none` | No honeypots (the control condition) |
| `semantic`, `prompt_injection`, `link_graph` | Only that honeypot |

```bash
HONEYPOT_VARIANT=none uvicorn app.main:app                      # bash
$env:HONEYPOT_VARIANT = "none"; uvicorn app.main:app            # PowerShell
```

A variant that is not active behaves as if it does not exist: its pages return
404, the places that advertise it (the visible link, the JSON-LD entry or the robots.txt entry) are
left out, and requests to its path are not logged as trap hits. `/health` reports
the active setting.

## Running the agents

Start the server first. Run records are written to `agent_runs/`, which is not
committed.

```bash
# Playwright baseline
python -m agents.playwright_baseline.run
python -m agents.playwright_baseline.run --ignore-robots

# Crawl4AI (Ollama must be running and the model pulled: ollama pull llama3.2)
crawl4ai-setup                   # once
python -m agents.crawl4ai_scraper.run --input-format markdown
python -m agents.crawl4ai_scraper.run --input-format html

# Synthetic human-behaviour baseline (a different seed gives a different session;
# --time-scale 0.2 makes the pauses five times shorter)
python -m agents.human_baseline.run --seed 42

# Claude computer use runs in Docker: a real browser window on a virtual screen.
# The first command builds the image (a few minutes, once); the others do nothing unless told to.
python -m agents.claude_computer_use.docker_run --build                           # build the image
python -m agents.claude_computer_use.docker_run --env-check                       # free check
python -m agents.claude_computer_use.docker_run --confirm-spend --max-iterations 3   # PAID; needs ANTHROPIC_API_KEY
```

The Claude agent needs Docker running, but not the `anthropic` package on your own
computer (it is installed in the image). The container reaches the server at
`host.docker.internal`, so start the server first (`uvicorn app.main:app`). The
free `--env-check` saves three screenshots to `agent_runs/claude_computer_use/`
(the start page, scrolled, and after typing an address), and reports whether a typed
address worked and whether other websites are blocked. The browser in the
container can reach only the test site; your API key is passed to the container
from your environment and is never written to a file.

The older single-page environment (a headless page with no address bar) is still
available without Docker as `python -m agents.claude_computer_use.run --env-check`,
for debugging.

```
# Claude text browser runs on your computer (needs `pip install anthropic`).
python -m agents.claude_text_browser.run --env-check                        # free: shows the page text Claude would be given
python -m agents.claude_text_browser.run --confirm-spend --max-iterations 3   # PAID; needs ANTHROPIC_API_KEY
```

The Playwright and Claude runs record the `hp_session` cookie, so they can be
joined to the server logs by session id. Crawl4AI cannot read the cookie, so its
runs are matched to the logs by time window.

## Running the experiment

The scheduler in `experiment/` plans and runs the experiment. A plan lists every
run in a randomised order, one block per repetition round, and gives each run a
label such as `crawl4ai_html__link_graph__r03` (agent, condition, repetition). The
same seed always produces the same plan. For each run the scheduler starts its own
server with the right `HONEYPOT_VARIANT`, runs the agent, stops the server and
saves the agent's record under the run label.

Stop any server you started yourself first: the scheduler needs port 8000.

```bash
# Create a plan (written to experiment/plans/pilot.json)
python -m experiment plan --name pilot --agents playwright_baseline,playwright_ignore_robots,crawl4ai_markdown,crawl4ai_html --reps 2

# Show what would run, then run it
python -m experiment run --plan pilot
python -m experiment run --plan pilot --execute

# Progress, and picking up again after an interruption (finished runs are skipped)
python -m experiment status --plan pilot
python -m experiment run --plan pilot --execute

# Look for runs that finished but did not really take place (for example a crawl that
# fetched nothing), mark them as failed and rerun them
python -m experiment check --plan pilot --apply
python -m experiment run --plan pilot --execute --retry-failed
```

The server logs build up across runs, and the scheduler does not touch them. After
a batch of runs, export each run's server-side records, and empty the logs before
a recording session so test traffic does not mix with results:

```bash
python -m experiment logs status                  # row counts
python -m experiment logs export --plan pilot     # one file per run, plus summary.csv
python -m experiment logs reset                   # shows what would be deleted
python -m experiment logs reset --yes             # empties request_log, trap_hit_event and client_event
```

Each export file holds the requests and the page events the server logged during
that run, marked by whether they came from the agent's own session. Export before resetting, because
reset deletes the only copy of the server-side data.

Runs that use the paid Claude agent are left out unless `--confirm-spend` is also
given, and nothing is run at all without `--execute`. Results go to
`agent_runs/experiment/<plan name>/` (not committed): a `manifest.json` with the
start and finish time and session id of every run, the agent records, the
agent and server output of each run, and the exported server records. The plan files are committed.

## Repository layout

```
app/
  config.py             Settings (environment variables or .env)
  db.py                 Async database engine and session
  main.py               FastAPI app: routes, middleware, table creation
  middleware.py         Logs every request and every honeypot hit (not the /_events beacons)
  models/               RequestLog, TrapHitEvent and ClientEvent tables
  events.py             Receives the page events posted to /_events
  site/                 The legitimate decoy pages, robots.txt and sitemap
  honeypots/
    schemas.py          Design schemas for the three variants
    specs.py            The concrete specs
    validation.py       Checks that every failure mode is covered
    active.py           Which variants are switched on (HONEYPOT_VARIANT)
    content.py          Synthetic page content (Faker)
    routes.py           The three honeypot routes and path helpers
agents/
  playwright_baseline/  Mechanical control crawler
  crawl4ai_scraper/     Crawl4AI harness using a local Ollama model
  claude_computer_use/  Claude computer-use harness (guarded against accidental spend)
    desktop.py          Real browser on a virtual screen (the environment used)
    x11.py              Screen capture, mouse and keyboard through the X server
    docker_run.py       Runs the agent in the Docker image from the host
    environment.py      Older headless-page environment, kept for debugging
  claude_text_browser/  Same model, text view of pages (browser.py, agent_loop.py, run.py)
docker/claude-desktop/  Dockerfile for the Claude environment
  human_baseline/       Scripted human-like browsing, for the false-positive rate
  shared/task.py        The task text shared by the LLM-based agents
experiment/             Run planning and the experiment runner
  plans/                Saved run plans
docs/PROTOCOL.md       Experiment protocol: design, measures and limitations
tests/                  Unit tests
docker-compose.yml      Local Postgres
PROGRESS.md             Status by phase
```

## Status

Phases 0 to 5 are complete, except that the Claude computer-use agent has not yet
been run. Phase 6 (experiment design) is complete and the protocol is in
`docs/PROTOCOL.md`; it was revised after being checked against the research
proposal (see section 8.1 of the protocol). The experiment itself (Phases 7 to 11)
has not started. See
`PROGRESS.md` for details and known limitations.

## About the data

All page content, company names, figures and identifiers are synthetic. No real
organisation or person is referenced, and the contact address on the site uses
the reserved `.invalid` domain. The ethics documentation for the project is held
separately and is not part of this repository.