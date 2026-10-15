"""
Routes for the three honeypot variants, and helpers that let the logging
middleware recognise honeypot paths.

  - SEMANTIC_TRAP_PATH: not linked from the navigation; referenced only by
    the JSON-LD data on the homepage (app/site/content.py).
  - PROMPT_INJECTION_TRAP_PATH: linked from a blog post through an anchor
    with no visible text.
  - DYNAMIC_GRAPH_BASE_PATH/{n}: a chain of pages that robots.txt disallows.

A route returns 404 when its variant is not active (see active.py).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.honeypots.active import is_variant_active
from app.honeypots.content import (
    render_dynamic_graph_page,
    render_prompt_injection_trap_page,
    render_semantic_trap_page,
)
from app.honeypots.specs import DYNAMIC_LINK_GRAPH_TRAP, PROMPT_INJECTION_TRAP, SEMANTIC_TRAP

SEMANTIC_TRAP_PATH = "/internal/reports/q3-export-2026"
PROMPT_INJECTION_TRAP_PATH = "/documents/vendor-notes"
DYNAMIC_GRAPH_BASE_PATH = "/archive/restricted/page"

_DYNAMIC_GRAPH_PATH_RE = re.compile(rf"^{re.escape(DYNAMIC_GRAPH_BASE_PATH)}/(\d+)$")

router = APIRouter()


def is_honeypot_path(path: str) -> str | None:
    """Return the variant_id if `path` belongs to an active honeypot, otherwise None."""
    variant_id = None
    if path == SEMANTIC_TRAP_PATH:
        variant_id = SEMANTIC_TRAP.variant_id
    elif path == PROMPT_INJECTION_TRAP_PATH:
        variant_id = PROMPT_INJECTION_TRAP.variant_id
    elif _DYNAMIC_GRAPH_PATH_RE.match(path):
        variant_id = DYNAMIC_LINK_GRAPH_TRAP.variant_id
    if variant_id is not None and is_variant_active(variant_id):
        return variant_id
    return None


def graph_depth_for_path(path: str) -> int | None:
    match = _DYNAMIC_GRAPH_PATH_RE.match(path)
    return int(match.group(1)) if match else None


@router.get(SEMANTIC_TRAP_PATH, response_class=HTMLResponse)
async def semantic_trap_page() -> str:
    if not is_variant_active(SEMANTIC_TRAP.variant_id):
        raise HTTPException(status_code=404)
    return render_semantic_trap_page()


@router.get(PROMPT_INJECTION_TRAP_PATH, response_class=HTMLResponse)
async def prompt_injection_trap_page() -> str:
    if not is_variant_active(PROMPT_INJECTION_TRAP.variant_id):
        raise HTTPException(status_code=404)
    html, _canary_token = render_prompt_injection_trap_page()
    # The token is not stored. Matching tokens against agent output is
    # planned as an offline analysis step.
    return html


@router.get(DYNAMIC_GRAPH_BASE_PATH + "/{page_number}", response_class=HTMLResponse)
async def dynamic_graph_trap_page(page_number: int) -> str:
    if not is_variant_active(DYNAMIC_LINK_GRAPH_TRAP.variant_id):
        raise HTTPException(status_code=404)
    if page_number < 1 or page_number > DYNAMIC_LINK_GRAPH_TRAP.max_depth:
        raise HTTPException(status_code=404)
    html, _doc_id = render_dynamic_graph_page(page_number)
    return html