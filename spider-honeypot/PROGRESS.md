# Progress

Last updated: 14 October 2026.

Status key: **Done**, **Partly done**, **Not started**.

| Phase | Description | Status |
|---|---|---|
| 0 | Project scaffolding and decisions | Done |
| 1 | Design specification for each honeypot variant | Done |
| 2 | Decoy web application | Done |
| 3 | Build the three honeypot variants | Done |
| 4 | Logging and instrumentation | Done |
| 5 | Agent and scraper harnesses | Partly done |
| 6 | Experiment design | In progress |
| 7 | Pilot run | Not started |
| 8 | Full controlled experiment | Not started |
| 9 | Data analysis | Not started |
| 10 | Cross-check against research questions | Not started |
| 11 | Write-up | Not started |

## Phase 0: Scaffolding and decisions

- Stack: Python and FastAPI, with Postgres accessed through async SQLAlchemy.
- Settings loader, database setup, health endpoint and a Docker Compose file
  for a local Postgres.
- Everything runs on a single local machine; the repository is private.

## Phase 1: Design specification

- Pydantic schemas describing each honeypot variant: the failure mode it
  targets, how it is concealed, which agents it is aimed at and the signal used
  to detect a hit.
- Concrete specs for the three variants.
- A validation step that checks every failure mode from the literature review
  is targeted by at least one variant.
- Unit tests for the schemas and validation.

## Phase 2: Decoy web application

- A plain, fictional company site, Dunwoodie Data Analytics, with home,
  product, pricing, blog and contact pages.
- `robots.txt` with two Disallow entries (one harmless, one covering the
  link-graph trap) and a sitemap that lists only legitimate pages.
- Discovery points for two of the honeypots: JSON-LD data on the homepage and a
  link with no visible text in a blog post.

## Phase 3: Honeypot variants

- Synthetic content generated with Faker for all three variants.
- Routes for the semantic trap, the prompt-injection trap (canary token in an
  HTML comment, unique per page load) and the link-graph trap (a chain of 14
  pages, 404 beyond the last).
- Not done: LLM-written prose for the semantic trap. Faker content only.

## Phase 4: Logging

- `RequestLog` for every request and `TrapHitEvent` for honeypot hits, written
  automatically by middleware and keyed by a session cookie.
- Tables are created at start-up. There are no migrations.
- Matching canary tokens against agent output is left to the analysis phase.

## Phase 5: Agent harnesses

- Playwright baseline: done and run against the site.
- Crawl4AI with a local Ollama model: done and run in both markdown and html
  input modes.
- Claude computer use: built and tested offline, not yet run. It is protected by
  an explicit spending flag, and real runs are planned for Phase 8 to avoid API
  cost until results are being recorded.

## Phase 6: Experiment design (in progress)

Done:
- A variant switch (`HONEYPOT_VARIANT`) so each honeypot can be tested on its own
  and a control with no honeypots can be run.
- One task prompt shared by the Crawl4AI and Claude agents (`agents/shared/task.py`).
- A seeded run scheduler (`experiment/`): randomised block design, one label per
  run (agent, condition, repetition), a server started per run with the right
  variant, and a resumable manifest. Paid runs need an extra flag.
- Log helpers (`experiment/logs.py`): empty the server logs, and export each
  run's server-side records with its label plus a summary table.

- A seeded, human-like browsing baseline (`agents/human_baseline/`) for the
  false-positive rate. It follows visible links only, with varied pauses, page
  counts and some back-navigation. The literature (Tanaka et al., Scripcariu et
  al.) supports the pattern but gives no numbers, so the parameter values are
  chosen, not measured, and are stated as such.

To do:
- A written protocol: run matrix, number of repetitions and exact definitions of
  the four metrics (detection rate, false-positive rate, time to detection and
  trap depth).

## Phases 7 to 11

- Phase 7: a small pilot with the free agents. Check the trap parameters
  (chain length, idle timeout, injection surface) and the run matrix.
- Phase 8: run the full experiment, including the paid Claude agent.
- Phase 9: join server logs to run records, check transcripts for canary tokens
  and compute detection metrics.
- Phase 10: compare results with the research questions.
- Phase 11: write up.

## Decisions

- No fake email honeytokens are used. Document IDs and canary strings give the
  same detection signal without any privacy questions.
- Crawl4AI uses a local open-weight model through Ollama, so it needs no API key
  and costs nothing to run, in contrast to the paid Claude agent.
- The Claude agent controls a headless Playwright browser with no address bar,
  so it can only click what is visible on the page.

## Known limitations

- The human baseline is synthetic. It cannot show how real visitors behave, and
  it is expected to give a false-positive rate of zero by construction, because
  the honeypots are only reachable through links a person cannot see or does not
  have. Its value is confirming that the concealment holds in a rendering
  browser. Real human data is left to future work.
- The human baseline does not model time of day, which has no effect on a
  local testbed.
- Crawl4AI sometimes silently drops a page from its results when the returned
  URL differs from the queued URL. The server's request log is treated as the
  source of truth for which pages were visited.
- Crawl4AI's markdown input removes HTML comments, so the prompt-injection trap
  is invisible in that mode. The html mode exposes it, so both are run.
- Crawl4AI does not expose browser cookies, so its runs are matched to server
  logs by time window instead of session id.
- The scroll distance per step in the Claude environment (100 pixels) is an
  assumption and may need adjusting.

## Open items

- The shared task prompt is a first version and may be adjusted after the pilot.
- Trap parameters (14 pages, 120 second idle timeout, HTML-comment injection
  only) are initial values to review after the pilot.