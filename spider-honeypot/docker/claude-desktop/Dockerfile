# The environment for the Claude computer-use agent: a virtual screen (Xvfb) and a real
# Chromium window, controlled through the X server. Built and run for you by
#   python -m agents.claude_computer_use.docker_run
# The project code is not copied in; it is mounted when the container runs, so changing
# the agent code never needs a rebuild. Only a change to this file does.
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONPATH=/app \
    AGENT_OUTPUT_DIR=/out

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Keep the Playwright version the same as requirements.txt
ARG PLAYWRIGHT_VERSION=1.62.0
RUN pip install --no-cache-dir playwright==${PLAYWRIGHT_VERSION} anthropic python-xlib pillow \
    && playwright install --with-deps chromium

WORKDIR /app