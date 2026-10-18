# Progress


Status key: **Done**, **Partly done**, **Not started**.

| Phase | Description | Status |
|---|---|---|
| 0 | Project scaffolding and decisions | Done |
| 1 | Design specification for each honeypot variant | Done |
| 2 | Decoy web application | Done |
| 3 | Build the three honeypot variants | Done |
| 4 | Logging and instrumentation | Done |
| 5 | Agent and scraper harnesses | Partly done |
| 6 | Experiment design | Done |
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
- Discovery points: a visible link to each honeypot in the blog (the Q3 export in
  the first post, the vendor notes in the second, the restricted archive on the
  blog index), plus the JSON-LD entry on the homepage and the robots.txt entry.
  A link is present only while its variant is active. The earlier design hid the
  links, which a screenshot-based agent could not see.

## Phase 3: Honeypot variants

- Synthetic content generated with Faker for all three variants.
- Routes for the semantic trap, the prompt-injection trap (the instruction and a
  canary token appear in an HTML comment and again in small visible text, each
  with its own token, unique per page load) and the link-graph trap (a chain of 14
  pages, 404 beyond the last).
- Not done: LLM-written prose for the semantic trap. Faker content only.

## Phase 4: Logging

- `RequestLog` for every request and `TrapHitEvent` for honeypot hits, written
  automatically by middleware and keyed by a session cookie.
- A script in every page reports DOM events (view, click, leave with time on the
  page, scroll depth and mouse and key counts) to `/_events`; they are stored in
  `ClientEvent` and are not logged as page requests. This gives the three log
  levels the proposal describes (HTTP, DOM event, session).
- Tables are created at start-up. There are no migrations.
- Matching canary tokens against agent output is left to the analysis phase.

## Phase 5: Agent harnesses

- Playwright baseline: done and run against the site.
- Crawl4AI with a local Ollama model: done and run in both markdown and html
  input modes.
- Claude text browser (`agents/claude_text_browser/`): added 17 October 2026 so that Claude can be compared with itself across perception (screenshots against page text and link addresses). Offline tests pass; the paid capped test has not been run yet.
- Claude computer use: built and tested offline; the capped 3-iteration paid test cost about $0.05. It is protected by
  an explicit spending flag, and real runs are planned for Phase 8 to avoid API
  cost until results are being recorded. It now controls a real Chromium window
  (tab bar, address bar) on a virtual screen (Xvfb) inside a Docker container,
  using screen capture and OS-level mouse and keyboard input, so it can click
  links, type addresses and use keyboard shortcuts. The browser can reach only the
  test site. The scheduler runs it through `agents/claude_computer_use/docker_run.py`.
  The desktop environment was tested on a virtual screen in the development
  sandbox (including the full agent loop with a scripted model); the Docker image
  could not be built there, so `docker_run --env-check` on the researcher's computer
  is the first real test of the container.

## Phase 6: Experiment design

- A variant switch (`HONEYPOT_VARIANT`) so each honeypot can be tested on its own
  and a control with no honeypots can be run.
- One task prompt shared by the Crawl4AI and Claude agents (`agents/shared/task.py`).
- A seeded run scheduler (`experiment/`): randomised block design, one label per
  run (agent, condition, repetition), a server started per run with the right
  variant, and a resumable manifest. Paid runs need an extra flag.
- Log helpers (`experiment/logs.py`): empty the server logs, and export each
  run's server-side requests and page events with its label plus a summary table.
- A sixth configuration, `playwright_ignore_robots`: the baseline crawler without
  robots.txt, so a traditional scraper can reach the link-graph chain.
- A seeded, human-like browsing baseline (`agents/human_baseline/`) for the
  false-positive rate. It follows visible links only, with varied pauses, page
  counts and some back-navigation. The literature (Tanaka et al., Scripcariu et
  al.) supports the pattern but gives no numbers, so the parameter values are
  chosen, not measured, and are stated as such.
- A written protocol (`docs/PROTOCOL.md`): conditions, run matrix and
  repetitions (240 runs with the extra configurations), ordering, the procedure for each run, exact definitions
  of the four measures plus canary compliance, the analysis plan and known
  limitations. It is frozen after the pilot; later changes are listed in its
  amendments section.

## Review against the proposal (before the pilot)

The design was checked against the research proposal and four gaps were fixed:
traps were hidden from screenshot-based agents (now visible links), Claude had no
address bar (now a real browser in Docker), logging was HTTP only (now page events
too) and the link-graph chain could not be reached (visible lure plus a crawler
that ignores robots.txt). Details are in section 8.1 of the protocol.

## Phases 7 to 11

- Phase 7: a small pilot with the free agents (2 repetitions per condition),
  after `docker_run --env-check` passes. Check that every harness completes, how
  long runs take, whether each trap is reached by the agents expected to reach it
  (the link-graph chain by the crawler that ignores robots.txt, the lures by the
  others), whether the human baseline's false-positive rate is plausible, and the
  trap parameters (chain length, idle timeout, injection surface). Then freeze the
  protocol: done in protocol v1.4 (pilot3 results and capped Claude tests recorded);
  `python -m experiment freeze` writes the seed and environment.
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
- The honeypot links are visible, because the proposal expects agents to be
  attracted by content, and an agent that works from screenshots cannot see hidden
  links. The cost is that the false-positive rate becomes meaningful.
- The Claude agent works from screenshots only. Hybrid commercial agents that also
  read the page structure are not tested.
- The Claude agent runs in Docker and the other agents on the host. The window has
  no window manager and no drawn pointer.

## Known limitations

- The human baseline is synthetic. It cannot show how real visitors behave. Now
  that the traps are reached by visible links it picks links without modelling
  curiosity, so its false-positive rate is a property of the site layout under an
  assumed behaviour, not a measure of real people. Real human data is left to
  future work.
- The human baseline does not model time of day, which has no effect on a
  local testbed.
- Crawl4AI refuses to fetch pages when memory use is above 95% and still exits
  normally. This hit 7 of 16 pilot runs. The guard is now switched off, a run with
  unfetched pages is reported as invalid and rerun (`experiment check`), and the
  html mode has the same page limit as the markdown mode (it had 5).
- Crawl4AI's link depth limit of 4 means it can reach at most pages 1 to 3 of the
  link-graph chain.
- Crawl4AI sometimes silently drops a page from its results when the returned
  URL differs from the queued URL. The server's request log is treated as the
  source of truth for which pages were visited.
- Crawl4AI's markdown input removes HTML comments, so only the visible copy of
  the prompt-injection instruction can be seen in that mode. The html mode sees
  both, so both are run.
- Crawl4AI does not expose browser cookies, so its runs are matched to server
  logs by time window instead of session id.
- The scroll distance per step in the Claude environment (100 pixels) is an
  assumption and may need adjusting.

## Open items

- The shared task prompt is a first version and may be adjusted after the pilot.
- Trap parameters (14 pages, 120 second idle timeout, injection in a comment and
  as visible text) are initial values to review after the pilot.