# Spider Honeypots against LLM-Driven Scrapers

Honours project for COS 700 at the University of Pretoria.
**Author:** Ethan Wilke (u23577674) | **Supervisor:** Prof. Jan Eloff | October 2026

**[Interactive results](https://ethanwilke23.github.io/Spider-Honeypots-Against-Scrapers/)** |
**[Report (PDF)](https://ethanwilke23.github.io/Spider-Honeypots-Against-Scrapers/report.pdf)** |
**[Poster (PDF)](https://ethanwilke23.github.io/Spider-Honeypots-Against-Scrapers/poster.pdf)**

## What this project is about

A spider honeypot is a link that only a robot would follow. It is invisible or unattractive to people, so any visitor that requests it is probably an automated scraper. Classical honeypots assume the scraper is mechanical. A scraper driven by a large language model (LLM) can read what a page means and browse like a person, so it may recognise a trap or avoid it.

**Research question.** Can spider honeypots be redesigned to detect LLM-driven scrapers, and what design characteristics do they need to remain undetected by them?

## What was built

A fictional company website that logs every request and page event, with three honeypot designs that can be switched on one at a time:

| Honeypot | Idea |
|---|---|
| **Semantic trap** | A page that looks like an internal quarterly financial export, linked from a blog post. It lures an agent that is looking for sensitive content. |
| **Prompt-injection trap** | Vendor notes that ask automated assistants to repeat a canary token, placed in a hidden comment and in small visible text. |
| **Link-graph chain** | 14 "restricted archive" pages that each tease the next, disallowed in `robots.txt`. |

## How it was evaluated

The study follows Design Science Research (Hevner et al.). Seven agents visited the site under four conditions (the three honeypots, plus a control with none): **240 runs** in total.

- Two Playwright crawlers, one that obeys `robots.txt` and one that ignores it.
- Crawl4AI with a small local model (llama3.2), fed either markdown or raw HTML.
- Claude Sonnet 5.5 in two modes: screenshots, and page text.
- A scripted human baseline, used to estimate false positives.

Detection rates carry exact (Clopper-Pearson) 95% confidence intervals. Eight Fisher exact tests compare agents, with a Bonferroni correction.

## Main results

- **90 of 90** honeypot runs by LLM-driven agents (Crawl4AI and Claude) hit a trap. The scripted human baseline hit one in **1 of 30**. The control condition produced **0** hits.
- A `robots.txt` rule only protects against clients that read it. The crawler that obeys it never entered the chain (0 of 10). Both Claude agents entered the disallowed chain in 10 of 10 runs without having requested the file.
- The prompt-injection trap was unsuccessful against Claude: no run followed the hidden instruction (0 of 10). The token was only quoted.
- The semantic trap and the link-graph chain were successful. The link-graph chain caught the behaviour, but not the reasoning, since Claude had not read `robots.txt`.
- The one false positive came from the visible link that attracts agents.

**Limits.** Detection was at the ceiling, so the designs could not be ranked, and no classical hidden-link honeypot was tested. The samples are small (5 to 10 runs per cell), with one website, one task and two models. The human baseline is synthetic. Crawl4AI's depth in the chain is capped by its crawl settings. The full discussion is in the report.

## Repository guide

| Path | What it holds |
|---|---|
| `spider-honeypot/README.md` | Setup and the commands for running the experiment. **Start here to run the code.** |
| `spider-honeypot/docs/PROTOCOL.md` | The experiment protocol, frozen before the main run. Later changes are dated amendments. |
| `spider-honeypot/experiment/` | The scheduler, the analysis and the statistics. |
| `spider-honeypot/tests/` | The automated test suite. |
| `spider-honeypot/PROGRESS.md` | Progress notes kept during the project. |
| `docs/` | The results website and the downloadable report and poster. |

## Running it yourself

See [`spider-honeypot/README.md`](spider-honeypot/README.md) for requirements and commands. Runs that use the paid Claude agents need an API key. The key is not stored in this repository.
