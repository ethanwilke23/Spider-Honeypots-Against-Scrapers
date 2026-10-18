"""
Freeze record: the main-run seed and the environment the experiment ran in.

`python -m experiment freeze` collects the facts that a reader of the report needs in order to
repeat the experiment (operating system, Python and package versions, the Chromium build,
the Ollama model's digest, the Docker image, the Claude model names, the git commit, and
hashes of the protocol and the task text), draws the main seed once, and writes
docs/freeze_record.json. The seed is drawn from the operating system's random source
(secrets.randbelow) and is never redrawn unless --force is given, so the order of runs
cannot be tuned after seeing results.

Nothing here costs money or changes the logs.
"""
from __future__ import annotations

import hashlib
import json
import platform
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = ROOT / "docs" / "freeze_record.json"
PACKAGES = ["playwright", "Crawl4AI", "anthropic", "fastapi", "uvicorn", "SQLAlchemy", "asyncpg", "httpx", "pydantic", "Faker"]
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"
DOCKER_IMAGE = "spider-honeypot-claude-desktop"


def draw_seed() -> int:
    return secrets.randbelow(10**6)


def _run(command: list[str], timeout: int = 20) -> str | None:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def package_versions() -> dict[str, str | None]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def chromium_version() -> str | None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                return browser.version
            finally:
                browser.close()
    except Exception:
        return None


def ollama_info() -> dict:
    info: dict = {"model": OLLAMA_MODEL, "digest": None, "size_bytes": None, "parameter_size": None, "quantization": None, "server_version": None}
    try:
        import httpx

        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        for m in tags:
            if m.get("name", "").split(":")[0] == OLLAMA_MODEL:
                details = m.get("details", {})
                info.update(
                    tag=m.get("name"),
                    digest=m.get("digest"),
                    size_bytes=m.get("size"),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                )
                break
        info["server_version"] = httpx.get(f"{OLLAMA_URL}/api/version", timeout=5).json().get("version")
    except Exception:
        pass
    return info


def claude_models() -> dict:
    from agents.claude_computer_use.agent_loop import DEFAULT_MODEL as desktop_model
    from agents.claude_text_browser.agent_loop import DEFAULT_MODEL as text_model

    return {"claude_computer_use": desktop_model, "claude_text_browser": text_model}


def task_texts() -> dict:
    from agents.shared.task import AGENTS_WITH_TASK, get_task_instruction

    return {agent: hashlib.sha256(get_task_instruction(agent).encode("utf-8")).hexdigest() for agent in AGENTS_WITH_TASK}


def protocol_version() -> str | None:
    try:
        for line in (ROOT / "docs" / "PROTOCOL.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("Version "):
                return line.split("(")[0].replace("Version", "").strip()
    except OSError:
        pass
    return None


def collect_environment() -> dict:
    dirty = _run(["git", "status", "--porcelain"])
    return {
        "operating_system": platform.platform(),
        "python": sys.version.split()[0],
        "packages": package_versions(),
        "chromium": chromium_version(),
        "ollama": ollama_info(),
        "docker_version": _run(["docker", "--version"]),
        "docker_image": {"name": DOCKER_IMAGE, "id": _run(["docker", "image", "inspect", DOCKER_IMAGE, "--format", "{{.Id}}"])},
        "claude_models": claude_models(),
        "git_commit": _run(["git", "rev-parse", "HEAD"]),
        "git_uncommitted_changes": None if dirty is None else bool(dirty),
        "protocol_version": protocol_version(),
        "protocol_sha256": sha256_of(ROOT / "docs" / "PROTOCOL.md"),
        "task_text_sha256": task_texts(),
    }


def build_record(seed: int, environment: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {"frozen_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "main_seed": seed, "environment": environment}


def missing_items(environment: dict) -> list[str]:
    """What could not be recorded, so the researcher can fix it before the main run."""
    problems = []
    if not environment["chromium"]:
        problems.append("Chromium version (is Playwright's Chromium installed?)")
    if not environment["ollama"]["digest"]:
        problems.append(f"Ollama model digest (is Ollama running and `ollama pull {OLLAMA_MODEL}` done?)")
    if not environment["docker_image"]["id"]:
        problems.append("Docker image id (build it: python -m agents.claude_computer_use.docker_run --build)")
    if environment["git_commit"] is None:
        problems.append("git commit")
    if environment["git_uncommitted_changes"]:
        problems.append("there are uncommitted changes: commit everything first so the commit identifies the code that runs")
    for name in ("playwright", "Crawl4AI", "anthropic"):
        if not environment["packages"].get(name):
            problems.append(f"package {name}")
    return problems


def load_freeze() -> dict | None:
    try:
        return json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None