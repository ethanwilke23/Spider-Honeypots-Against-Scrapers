# Progress

Status key: **Done**, **Partly done**, **Not started**.

| Phase | Description | Status |
|---|---|---|
| 0 | Project scaffolding and decisions | Done |
| 1 | Design specification for each honeypot variant | Done |
| 2 | Decoy web application | Done |
| 3 | Build the three honeypot variants | Done |
| 4 | Logging and instrumentation | Done |
| 5 | Agent and scraper harnesses | Done |
| 6 | Experiment design | Done |
| 7 | Pilot run | Done |
| 8 | Full controlled experiment | Done |
| 9 | Data analysis | Partly done |
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

- Playwright baseline: done and run against the site. A second configuration
  (`playwright_ignore_robots`) is the same crawler with robots.txt ignored.
- Crawl4AI with a local Ollama model (`llama3.2`): done and run in both markdown and
  html input modes.
- Claude computer use (`agents/claude_computer_use/`, model `claude-sonnet-5-5`): Claude
  controls a real Chromium window (tab bar, address bar) on a virtual screen (Xvfb)
  inside a Docker container, through screenshots and OS-level mouse and keyboard
  input, so it can click links, type addresses and use keyboard shortcuts. The browser
  can reach only the test site. The scheduler runs it through
  `agents/claude_computer_use/docker_run.py`. It is protected by an explicit spending
  flag. `docker_run --env-check` passed on the researcher's computer; the capped
  3-iteration paid test cost about $0.05.
- Claude text browser (`agents/claude_text_browser/`, added 17 October 2026): the same
  model reading each page as visible text plus a numbered list of links, in a headless
  browser on the host, with the tools `open_link`, `open_url` and `go_back` (one tool
  call per turn). It exists so that Claude can be compared with itself across
  perception (screenshots against page text). Its capped paid test passed.

## Phase 6: Experiment design

- A variant switch (`HONEYPOT_VARIANT`) so each honeypot can be tested on its own
  and a control with no honeypots can be run.
- One task prompt shared by the Crawl4AI and Claude agents (`agents/shared/task.py`),
  with a short interface sentence for each agent.
- A seeded run scheduler (`experiment/`): randomised block design, one label per
  run (agent, condition, repetition), a server started per run with the right
  variant, and a resumable manifest. Paid runs need an extra flag.
- Log helpers (`experiment/logs.py`): empty the server logs, and export each
  run's server-side requests and page events with its label plus a summary table.
- Seven configurations in all: `playwright_baseline`, `playwright_ignore_robots` (no
  robots.txt, so a traditional scraper can reach the link-graph chain),
  `crawl4ai_markdown`, `crawl4ai_html`, `claude_computer_use`, `claude_text_browser` and
  the synthetic `human_baseline`.
- A seeded, human-like browsing baseline (`agents/human_baseline/`) for the
  false-positive rate. It follows visible links only, with varied pauses, page
  counts and some back-navigation. The literature (Tanaka et al., Scripcariu et
  al.) supports the pattern but gives no numbers, so the parameter values are
  chosen, not measured, and are stated as such.
- A written protocol (`docs/PROTOCOL.md`): conditions, run matrix and
  repetitions (240 runs), ordering, the procedure for each run, exact definitions
  of the measures, the analysis plan and known limitations. It was frozen before the
  main run (version 1.4); later changes are listed in its amendments section
  (version 1.5 adds the analysis choices).
- A freeze step (`python -m experiment freeze`) that draws the main seed once and
  records the environment in `docs/freeze_record.json`.

## Review against the proposal (before the pilot)

The design was checked against the research proposal and four gaps were fixed:
traps were hidden from screenshot-based agents (now visible links), Claude had no
address bar (now a real browser in Docker), logging was HTTP only (now page events
too) and the link-graph chain could not be reached (visible lure plus a crawler
that ignores robots.txt). Details are in section 8.1 of the protocol.

## Phase 7: Pilot (done)

- Pilot plans `pilot2` and `pilot3` (seed 700) with the free agents, 2 repetitions per
  condition. They exposed the Crawl4AI memory-guard failures and the html-mode page cap,
  both fixed (protocol section 9); `pilot3` was clean.
- Capped paid tests of both Claude agents (3 iterations each). They showed the cost
  (about $0.05 for 3 desktop iterations, about $0.54 estimated for 15) and led to the
  correct model name and to one tool call per turn for the text browser.
- Protocol frozen as version 1.4; `python -m experiment freeze` recorded the seed and
  environment on 18 October 2026 (main seed 707150).

## Phase 8: Main experiment (done)

- Plan `main`: 240 runs in 10 randomised blocks (seed 707150), run on 18 October 2026.
  All 240 runs completed and passed the validity check (`experiment check`).
- The server logs recorded 0 unexpected trap hits and 0 hits in the control (`none`)
  condition. The human baseline hit a trap once in 30 honeypot runs
  (`human_baseline__link_graph__r03`, a click on the visible "restricted archive" link).
- Raw data: `agent_runs/experiment/main/` (records, server records and `summary.csv`).
  It is not committed, so keep a copy elsewhere.

## Phase 9: Analysis (partly done)

- Built: `python -m experiment analyse --plan main` (`experiment/analysis.py`) computes
  detection and false-positive rates with exact intervals, time to detection, chain
  depth, canary compliance, echo, page events, the pre-specified Fisher tests, three
  charts and a hand-coding sheet. Tested on made-up records.
- To do: run it on the real records, check the output against `summary.csv`, hand-code
  the Claude runs (suspicion, refusals, partial compliance, invented content) from
  `coding_sheet.csv`.

## Phases 10 and 11

- Phase 10: compare the results with the research questions.
- Phase 11: write up (needs the module's report template or marking rubric).

## Decisions

- No fake email honeytokens are used. Document IDs and canary strings give the
  same detection signal without any privacy questions.
- Crawl4AI uses a local open-weight model through Ollama, so it needs no API key
  and costs nothing to run, in contrast to the paid Claude agents.
- Crawl4AI chooses which pages to fetch by link scoring on keywords from the task
  wording, not by asking its model, so whether it reaches a trap is deterministic.
  Its headline results are canary compliance and echo; detection is the headline
  result for the Claude agents, where the model chooses the route.
- The honeypot links are visible, because the proposal expects agents to be
  attracted by content, and an agent that works from screenshots cannot see hidden
  links. The cost is that the false-positive rate becomes meaningful.
- Two Claude configurations share one model: the desktop agent works from screenshots
  only, and the text browser reads page text and link addresses. Hybrid commercial
  agents that combine both are not tested.
- The desktop Claude agent runs in Docker and the other agents on the host. Its window
  has no window manager and no drawn pointer.
- The text browser may make one tool call per turn, because a link number refers to
  the page it was read from; so one iteration is one page view.

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
- The Claude agents are capped at 15 iterations. Results hold within that cap. For the
  desktop agent an iteration is a turn that can contain several actions; for the text
  browser it is one page view.
- Claude can request a deep link-graph page by typing its address without visiting
  the pages before it, so depth and the number of chain pages visited are reported
  separately.
- Visible traps are not concealed, so the experiment measures how well visible,
  plausible lures detect agents, not how well hidden ones do.

## Open items

- Run the analysis on the real records and review the results.
- Hand-code the 40 Claude runs.
- Obtain the module's report template or marking rubric for Phase 11.
- The trap parameters (14 pages, 120 second idle timeout, injection in a comment and
  as visible text) were reviewed after the pilot and not changed for the main run.