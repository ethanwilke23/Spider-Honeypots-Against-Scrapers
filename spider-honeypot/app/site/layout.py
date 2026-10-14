"""
Shared HTML layout for the decoy site and the honeypot pages.

Honeypot pages use the same layout so they look consistent with the rest
of the site. The styling is deliberately plain: white background, one
accent colour and system fonts.
"""
from __future__ import annotations

NAV_ITEMS = [
    ("Home", "/"),
    ("Product", "/product"),
    ("Pricing", "/pricing"),
    ("Blog", "/blog"),
    ("Contact", "/contact"),
]

_STYLE = """
:root {
  --ink: #1c2530;
  --muted: #5b6673;
  --accent: #2f5d8a;
  --border: #e3e7eb;
  --bg: #ffffff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: var(--ink);
  background: var(--bg);
  line-height: 1.55;
}
header {
  border-bottom: 1px solid var(--border);
}
.nav-wrap {
  max-width: 960px;
  margin: 0 auto;
  padding: 18px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brand { font-weight: 600; font-size: 1.05rem; color: var(--ink); text-decoration: none; }
nav a {
  color: var(--muted);
  text-decoration: none;
  margin-left: 22px;
  font-size: 0.95rem;
}
nav a:hover { color: var(--accent); }
main { max-width: 720px; margin: 0 auto; padding: 48px 24px 72px; }
h1 { font-size: 1.9rem; margin: 0 0 18px; }
h2 { font-size: 1.3rem; margin: 36px 0 12px; }
p { color: var(--ink); margin: 0 0 16px; }
.muted { color: var(--muted); }
a.link { color: var(--accent); }
table { border-collapse: collapse; width: 100%; margin: 18px 0; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); font-size: 0.92rem; }
th { color: var(--muted); font-weight: 600; }
footer {
  border-top: 1px solid var(--border);
  padding: 28px 24px;
  color: var(--muted);
  font-size: 0.85rem;
}
.footer-wrap { max-width: 960px; margin: 0 auto; display: flex; justify-content: space-between; }
.blog-list { list-style: none; padding: 0; }
.blog-list li { margin-bottom: 22px; }
.blog-list a { color: var(--ink); font-weight: 600; text-decoration: none; }
.blog-list .date { color: var(--muted); font-size: 0.85rem; display: block; margin-top: 2px; }
"""


def render_page(title: str, body_html: str, extra_head: str = "") -> str:
    nav_links = "".join(f'<a href="{href}">{label}</a>' for label, href in NAV_ITEMS)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Dunwoodie Data Analytics</title>
<style>{_STYLE}</style>
{extra_head}
</head>
<body>
<header>
  <div class="nav-wrap">
    <a class="brand" href="/">Dunwoodie Data Analytics</a>
    <nav>{nav_links}</nav>
  </div>
</header>
<main>
{body_html}
</main>
<footer>
  <div class="footer-wrap">
    <span>&copy; 2026 Dunwoodie Data Analytics</span>
    <span>Pretoria, South Africa</span>
  </div>
</footer>
</body>
</html>"""