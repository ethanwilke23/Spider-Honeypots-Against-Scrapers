"""
Which honeypot variants are switched on.

The HONEYPOT_VARIANT setting (see app/config.py) lets one variant, all of
them, or none be active. This allows each experimental condition to be run
separately, including a control with no honeypots.

An inactive variant behaves as if it does not exist: its pages return 404,
the place where it is advertised (the visible link, JSON-LD entry or robots.txt entry)
is left out, and requests to its path are not logged as trap hits.
"""
from app.config import get_settings
from app.honeypots.specs import DYNAMIC_LINK_GRAPH_TRAP, PROMPT_INJECTION_TRAP, SEMANTIC_TRAP

_VARIANT_ID_BY_SETTING = {
    "semantic": SEMANTIC_TRAP.variant_id,
    "prompt_injection": PROMPT_INJECTION_TRAP.variant_id,
    "link_graph": DYNAMIC_LINK_GRAPH_TRAP.variant_id,
}


def active_setting() -> str:
    """Return the current HONEYPOT_VARIANT value."""
    return get_settings().honeypot_variant


def is_variant_active(variant_id: str) -> bool:
    setting = active_setting()
    if setting == "all":
        return True
    if setting == "none":
        return False
    return _VARIANT_ID_BY_SETTING[setting] == variant_id