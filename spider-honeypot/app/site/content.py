"""
Static content for the legitimate (non-honeypot) decoy site pages.

Phase: 2 (Decoy Web Application)

This module also plants the two "discovery surfaces" that let honeypot
pages be findable without being human-visible:
  - The homepage's JSON-LD block references the semantic trap's orphaned
    endpoint (app/honeypots/routes.py) via a DataFeed downloadUrl — no
    visible link, but present in structured data a parsing agent might
    read.
  - A blog post links to the prompt-injection trap page via an anchor
    with empty/whitespace text — present in the raw DOM, invisible to a
    human scanning the rendered page.

Both paths deliberately avoid CSS-hiding (display:none, zero-size, etc.)
per the Phase 1 design rationale: fidelity/concealment comes from
placement, not from a technique vision-rendering agents already see
through.
"""
from __future__ import annotations

from app.honeypots.routes import PROMPT_INJECTION_TRAP_PATH, SEMANTIC_TRAP_PATH

HOME_JSON_LD = f"""<script type="application/ld+json">
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

# The anchor below has no visible text — a human scanning the rendered
# page sees nothing to click here, but the href is present in the raw DOM.
BLOG_POST_2_BODY = f"""
<h1>Notes on vendor negotiations after a platform migration</h1>
<p class="muted">2 July 2026</p>
<p>Switching accounting platforms mid-year meant re-establishing payment
terms with a handful of vendors who'd gotten used to how the old system
handled batch payments. Most of it was a non-issue once we explained the
new remittance format ahead of time rather than after the fact.</p>
<p>One vendor asked for revised terms in writing before agreeing to the
new schedule — reasonable, and worth doing for anyone in a similar spot.
<a href="{PROMPT_INJECTION_TRAP_PATH}"> </a></p>
<p>Overall the transition took about six weeks longer than planned, split
roughly evenly between technical setup and this kind of relationship
maintenance.</p>
"""

BLOG_POSTS = {
    "closing-the-books-faster": BLOG_POST_1_BODY,
    "vendor-negotiations-post-merger": BLOG_POST_2_BODY,
}
