"""
Static page content for the legitimate decoy site.

Two pages also contain discovery points for the honeypots. Neither uses
CSS hiding:
  - The homepage JSON-LD block references the semantic trap's path.
  - A blog post links to the prompt-injection trap through an anchor with
    no visible text.

Each discovery point is included only while its variant is active.
"""
from __future__ import annotations

from collections.abc import Callable

from app.honeypots.active import is_variant_active
from app.honeypots.routes import PROMPT_INJECTION_TRAP_PATH, SEMANTIC_TRAP_PATH
from app.honeypots.specs import PROMPT_INJECTION_TRAP, SEMANTIC_TRAP


def home_json_ld() -> str:
    """JSON-LD block for the homepage. It is left out when the semantic trap is not active."""
    if not is_variant_active(SEMANTIC_TRAP.variant_id):
        return ""
    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "DataFeed",
  "name": "Dunwoodie Data Analytics Internal Reporting Feed",
  "dateModified": "2026-08-14",
  "downloadUrl": "{SEMANTIC_TRAP_PATH}"
}}
</script>"""


HOME_BODY = """
<h1>Bookkeeping and financial analytics, without the spreadsheet grind</h1>
<p>Dunwoodie Data Analytics connects to your accounting software and turns
transaction data into dashboards your finance team actually reads. No
manual exports, no month-end scramble.</p>
<p>Built for small and mid-sized finance teams across South Africa who
are done reconciling three spreadsheets to answer one question.</p>
<h2>What Dunwoodie does</h2>
<p>Automated reconciliation, cash flow forecasting, and a single view
across every account you connect. Set up takes about twenty minutes.</p>
<p><a class="link" href="/product">See how it works &rarr;</a></p>
"""

PRODUCT_BODY = """
<h1>Product</h1>
<p>Dunwoodie pulls data from your existing accounting stack and keeps a
running, always-current picture of cash position, outstanding invoices,
and month-over-month variance.</p>
<h2>Reconciliation</h2>
<p>Transactions are matched against your ledger automatically, with
exceptions flagged for review rather than buried in a spreadsheet.</p>
<h2>Forecasting</h2>
<p>A rolling 13-week cash flow forecast, rebuilt nightly from your latest
transaction data.</p>
<h2>Reporting</h2>
<p>Board-ready summaries generated on demand, without a finance analyst
having to rebuild the same deck every quarter.</p>
"""

PRICING_BODY = """
<h1>Pricing</h1>
<p>Straightforward, per-seat pricing. No setup fee, no annual lock-in.</p>
<table>
<tr><th>Plan</th><th>Seats</th><th>Monthly</th></tr>
<tr><td>Starter</td><td>Up to 3</td><td>R1,450</td></tr>
<tr><td>Growth</td><td>Up to 10</td><td>R3,900</td></tr>
<tr><td>Scale</td><td>Unlimited</td><td>Custom</td></tr>
</table>
<p class="muted">All plans include a 14-day trial. No card required.</p>
"""

CONTACT_BODY = """
<h1>Contact</h1>
<p>Questions about Dunwoodie, or want a walkthrough before you commit?
Reach out and someone from the team will get back to you within a
business day.</p>
<p class="muted">hello@dunwoodie-data-analytics-demo.invalid</p>
"""

BLOG_INDEX_BODY = """
<h1>Blog</h1>
<ul class="blog-list">
<li>
  <a href="/blog/closing-the-books-faster">Closing the books three days
  faster: what actually changed</a>
  <span class="date">14 August 2026</span>
</li>
<li>
  <a href="/blog/vendor-negotiations-post-merger">Notes on vendor
  negotiations after a platform migration</a>
  <span class="date">2 July 2026</span>
</li>
</ul>
"""

BLOG_POST_1_BODY = """
<h1>Closing the books three days faster: what actually changed</h1>
<p class="muted">14 August 2026</p>
<p>Most of the delay in a month-end close isn't the accounting itself —
it's chasing down the three or four transactions that don't match cleanly
between systems. We looked at where our own reconciliation process lost
the most time, and it wasn't where we expected.</p>
<p>The biggest single change was moving exception review to the start of
the week instead of the end. Exceptions caught on day one get resolved
before anyone's waiting on them; exceptions caught on day four become a
fire drill.</p>
<p>The second change was smaller but added up: batching bank-fee
line items instead of matching them individually. It's a handful of
minutes a week, but it was a handful of minutes every week.</p>
"""

def blog_post_2_body() -> str:
    """
    Second blog post. The anchor at the end of the second paragraph has no
    visible text, so a reader sees nothing to click, but the link is present
    in the HTML. It is left out when the prompt-injection trap is not active.
    """
    hidden_link = ""
    if is_variant_active(PROMPT_INJECTION_TRAP.variant_id):
        hidden_link = f'\n<a href="{PROMPT_INJECTION_TRAP_PATH}"> </a>'
    return f"""
<h1>Notes on vendor negotiations after a platform migration</h1>
<p class="muted">2 July 2026</p>
<p>Switching accounting platforms mid-year meant re-establishing payment
terms with a handful of vendors who'd gotten used to how the old system
handled batch payments. Most of it was a non-issue once we explained the
new remittance format ahead of time rather than after the fact.</p>
<p>One vendor asked for revised terms in writing before agreeing to the
new schedule — reasonable, and worth doing for anyone in a similar spot.{hidden_link}</p>
<p>Overall the transition took about six weeks longer than planned, split
roughly evenly between technical setup and this kind of relationship
maintenance.</p>
"""


# Each blog post is a function so its content can depend on the active variant.
BLOG_POSTS: dict[str, Callable[[], str]] = {
    "closing-the-books-faster": lambda: BLOG_POST_1_BODY,
    "vendor-negotiations-post-merger": blog_post_2_body,
}