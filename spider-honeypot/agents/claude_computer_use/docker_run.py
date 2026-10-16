"""
Runs the Claude computer-use agent inside the Docker image, from the host.

The experiment scheduler runs this module in place of agents.claude_computer_use.run.
It takes the same arguments and prints the same final line ("Run record written to
<path>"), so the scheduler treats it like any other agent. Behind the scenes:

  1. Builds the image from docker/claude-desktop/Dockerfile the first time (a few minutes).
  2. Starts a container with the project's agents/ folder mounted read-only, a folder for
     the run record mounted at /out, and the API key passed through from your environment.
  3. Inside, Claude controls a real browser window on a virtual screen
     (agents.claude_computer_use.run --desktop). The browser can reach only the test site.
  4. Copies nothing out except the run record, and removes the container afterwards.

The test server keeps listening on 127.0.0.1. From inside the container it is reached
as host.docker.internal, which Docker Desktop forwards to the host.

    python -m agents.claude_computer_use.docker_run --env-check          # free
    python -m agents.claude_computer_use.docker_run --confirm-spend --max-iterations 3   # paid
    python -m agents.claude_computer_use.docker_run --build              # rebuild the image
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_DIR = PROJECT_ROOT / "docker" / "claude-desktop"
HOST_OUTPUT_DIR = PROJECT_ROOT / "agent_runs" / "claude_computer_use"
IMAGE = "spider-honeypot-claude-desktop"
CONTAINER_HOST = "host.docker.internal"
CONTAINER_OUTPUT_DIR = "/out"

# The scheduler gives the agent 900 seconds; stop the container a little before that so it is
# removed here rather than left running when the scheduler gives up.
DEFAULT_TIMEOUT_SECONDS = 840

LOCAL_NAMES = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def container_base_url(base_url: str) -> str:
    """The same URL as seen from inside the container."""
    parsed = urlparse(base_url)
    if parsed.hostname in LOCAL_NAMES:
        netloc = CONTAINER_HOST + (f":{parsed.port}" if parsed.port else "")
        return urlunparse(parsed._replace(netloc=netloc))
    return base_url


def agent_arguments(args: argparse.Namespace, base_url: str) -> list[str]:
    """The arguments for agents.claude_computer_use.run inside the container."""
    command = ["python", "-m", "agents.claude_computer_use.run", "--desktop", "--base-url", base_url]
    if args.env_check:
        return command + ["--env-check"]
    command += ["--confirm-spend", "--max-iterations", str(args.max_iterations)]
    if args.model:
        command += ["--model", args.model]
    return command


def docker_run_command(
    container_name: str, agent_args: list[str], host_output_dir: Path, pass_api_key: bool, platform: str = sys.platform
) -> list[str]:
    command = [
        "docker", "run", "--rm", "--name", container_name,
        "--shm-size=1g",  # Chromium needs more shared memory than Docker's default 64 MB
        "-e", f"AGENT_OUTPUT_DIR={CONTAINER_OUTPUT_DIR}",
        "-v", f"{PROJECT_ROOT / 'agents'}:/app/agents:ro",
        "-v", f"{host_output_dir}:{CONTAINER_OUTPUT_DIR}",
    ]
    if platform.startswith("linux"):
        # Docker Desktop provides host.docker.internal itself; plain Docker on Linux does not.
        command += ["--add-host", f"{CONTAINER_HOST}:host-gateway"]
    if pass_api_key:
        command += ["-e", "ANTHROPIC_API_KEY"]  # copied from this process's environment, not written here
    return command + [IMAGE] + agent_args


def map_container_paths(output: str, host_output_dir: Path) -> str:
    """Rewrite /out/<file> in the container's output to the matching path on this computer."""
    return re.sub(rf"{re.escape(CONTAINER_OUTPUT_DIR)}/(\S+)", lambda m: str(host_output_dir / m.group(1)), output)


def _docker(*args: str, timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **kwargs)


def ensure_docker_ready() -> str | None:
    """Return an error message, or None when Docker is installed and its engine is running."""
    if not shutil.which("docker"):
        return "Docker is not installed or not on PATH."
    try:
        result = _docker("info", timeout=30)
    except subprocess.TimeoutExpired:
        return "Docker did not answer within 30 seconds. Is Docker Desktop still starting?"
    if result.returncode != 0:
        return "Docker is installed but its engine is not running. Start Docker Desktop and try again."
    return None


def ensure_image(force_build: bool = False) -> None:
    if not force_build and _docker("image", "inspect", IMAGE).returncode == 0:
        return
    print(f"Building the Docker image {IMAGE} (first time only; this takes a few minutes)...", flush=True)
    build = subprocess.run(["docker", "build", "-t", IMAGE, str(DOCKERFILE_DIR)])
    if build.returncode != 0:
        raise RuntimeError("The Docker image could not be built. See the messages above.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Claude computer-use agent in Docker (paid run is opt-in).")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-iterations", type=int, default=15)
    parser.add_argument("--env-check", action="store_true", help="Free: check the desktop environment (no API call).")
    parser.add_argument("--confirm-spend", action="store_true", help="REQUIRED for a real run: it makes paid API calls.")
    parser.add_argument("--build", action="store_true", help="Rebuild the Docker image, then continue (or stop if nothing else is asked).")
    parser.add_argument(
        "--require-image",
        action="store_true",
        help="Stop with a message if the image is not built yet instead of building it (the scheduler uses this, "
        "because a build would use up the run's time limit).",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    if not (args.env_check or args.confirm_spend or args.build):
        print(
            "Nothing was run and nothing was spent.\n\n"
            "  python -m agents.claude_computer_use.docker_run --env-check          (free)\n"
            "  python -m agents.claude_computer_use.docker_run --confirm-spend --max-iterations 3   (paid)"
        )
        return 2
    if not args.env_check and args.confirm_spend and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set in this environment, so nothing was run.")
        return 2

    problem = ensure_docker_ready()
    if problem:
        print(problem)
        return 2
    if args.require_image and not args.build and _docker("image", "inspect", IMAGE).returncode != 0:
        print(
            f"The Docker image {IMAGE} has not been built. Build it once with:\n"
            "  python -m agents.claude_computer_use.docker_run --build"
        )
        return 2
    try:
        ensure_image(force_build=args.build)
    except RuntimeError as exc:
        print(exc)
        return 1
    if not (args.env_check or args.confirm_spend):
        print("Image is built.")
        return 0

    HOST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    container_name = f"hp-claude-{os.getpid()}-{int(time.time())}"
    command = docker_run_command(
        container_name,
        agent_arguments(args, container_base_url(args.base_url)),
        HOST_OUTPUT_DIR,
        pass_api_key=not args.env_check,
    )
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=args.timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        print(f"The container ran for more than {args.timeout} seconds and was stopped. No run record was written.")
        return 1
    except KeyboardInterrupt:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        raise

    print(map_container_paths((result.stdout or "") + (result.stderr or ""), HOST_OUTPUT_DIR), end="")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())