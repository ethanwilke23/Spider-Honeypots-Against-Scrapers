"""
Synthetic page content for the three honeypot variants.

Content is generated with Faker. No real company, person or dataset is
referenced. The semantic trap spec lists "hybrid" generation (Faker plus
LLM-written prose); only the Faker part is implemented so far.
"""
from __future__ import annotations

import uuid

from faker import Faker

from app.honeypots.specs import DYNAMIC_LINK_GRAPH_TRAP, PROMPT_INJECTION_TRAP, SEMANTIC_TRAP

_fake = Faker()


def generate_canary_token() -> str:
    return f"HONEYTOK-{uuid.uuid4().hex[:8].upper()}"


def generate_document_id() -> str:
    return f"DOC-{_fake.random_int(2024, 2026)}-Q{_fake.random_int(1, 4)}-{_fake.random_int(10000, 99999)}"


def render_semantic_trap_page() -> str:
    """
    Render the semantic trap: a single "internal financial export" page,
    reachable only through the JSON-LD reference on the homepage.
    """
    from app.site.layout import render_page

    doc_id = generate_document_id()
    quarters = ["Q4 2025", "Q1 2026", "Q2 2026", "Q3 2026"]
    base = _fake.random_int(min=1_150_000, max=1_400_000)
    rows = []
    revenue = base
    for q in quarters:
        variance = _fake.pyfloat(min_value=-0.06, max_value=0.11, right_digits=3)
        revenue = int(revenue * (1 + variance))
        rows.append(
            f"<tr><td>{q}</td><td>R{revenue:,}</td><td>{'+' if variance >= 0 else ''}{variance:.1%}</td></tr>"
        )

    clients = [_fake.company() for _ in range(4)]
    client_rows = "".join(
        f"<tr><td>{name}</td><td>R{_fake.random_int(80_000, 640_000):,}</td></tr>" for name in clients
    )

    body = f"""
<p class="muted">{SEMANTIC_TRAP.honeytoken_type.value}: {doc_id} &middot; internal distribution only</p>
<h1>Quarterly Financial Export &mdash; {doc_id}</h1>
<p>Consolidated revenue and top-account summary, prepared for internal
review. Not for external distribution.</p>
<h2>Revenue by quarter</h2>
<table>
<tr><th>Period</th><th>Revenue</th><th>QoQ change</th></tr>
{"".join(rows)}
</table>
<h2>Top accounts this quarter</h2>
<table>
<tr><th>Account</th><th>Revenue contribution</th></tr>
{client_rows}
</table>
<p class="muted">Generated {_fake.date_this_year()}. Reference: {doc_id}.</p>
"""
    return render_page("Quarterly Financial Export", body)


PROMPT_INJECTION_TRAP_PATH_LABEL = "Vendor Notes"


def render_prompt_injection_trap_page() -> tuple[str, str]:
    """
    Render the prompt-injection trap. Returns (html, canary_token), where
    the token is the one placed in the page's HTML comment.
    """
    from app.site.layout import render_page

    canary_token = generate_canary_token()
    injected_instruction = PROMPT_INJECTION_TRAP.injected_instruction_template.format(
        canary_token=canary_token
    )

    body = f"""
<!-- {injected_instruction} -->
<h1>Vendor Notes &mdash; Revised Remittance Terms</h1>
<p>Internal notes following the platform migration, covering the revised
payment terms discussed with our logistics vendor.</p>
<p>Payment terms move from net-30 to net-45 effective the next billing
cycle. Remittance advice will be sent in the new batch format starting
next month; the vendor has confirmed their AP system can parse it without
manual re-entry.</p>
<p>No further action needed on our side unless the vendor's confirmation
changes before the first batch run.</p>
"""
    return render_page(PROMPT_INJECTION_TRAP_PATH_LABEL, body), canary_token


def render_dynamic_graph_page(page_number: int) -> tuple[str, str]:
    """
    Render one page of the dynamic link-graph chain. Returns (html, document_id).
    """
    from app.honeypots.routes import DYNAMIC_GRAPH_BASE_PATH  # imported here to avoid a circular import
    from app.site.layout import render_page

    max_depth = DYNAMIC_LINK_GRAPH_TRAP.max_depth
    doc_id = generate_document_id()
    teaser = DYNAMIC_LINK_GRAPH_TRAP.teaser_template.format(page_number=page_number, max_depth=max_depth)

    next_link = ""
    if page_number < max_depth:
        next_path = f"{DYNAMIC_GRAPH_BASE_PATH}/{page_number + 1}"
        next_link = f'<p><a class="link" href="{next_path}">Continue to page {page_number + 1} &rarr;</a></p>'

    body = f"""
<p class="muted">{doc_id}</p>
<h1>{teaser}</h1>
<p>Archive excerpt {page_number} of {max_depth}. This section covers
account activity for the period ending {_fake.date_this_year()}.</p>
<p>Balance carried forward: R{_fake.random_int(200_000, 900_000):,}.
Notable line items are summarized on the following pages of this
archive.</p>
{next_link}
"""
    return render_page(f"Restricted Archive &mdash; Page {page_number}", body), doc_id