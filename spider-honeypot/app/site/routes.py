"""
Routes for the legitimate decoy site pages, robots.txt and sitemap.xml.

robots.txt has two Disallow entries: /search-cache/, which leads nowhere,
and the dynamic-graph trap path (only while that variant is active). The
blog index links to that path, so a visible link conflicts with robots.txt.
The sitemap lists only legitimate pages; honeypot paths are never included.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.honeypots.active import is_variant_active
from app.honeypots.routes import DYNAMIC_GRAPH_BASE_PATH
from app.honeypots.specs import DYNAMIC_LINK_GRAPH_TRAP
from app.site.content import (
    BLOG_POSTS,
    CONTACT_BODY,
    HOME_BODY,
    PRICING_BODY,
    PRODUCT_BODY,
    blog_index_body,
    home_json_ld,
)
from app.site.layout import render_page

router = APIRouter()

_LEGIT_PATHS = ["/", "/product", "/pricing", "/blog", "/contact"] + [
    f"/blog/{slug}" for slug in BLOG_POSTS
]


@router.get("/", response_class=HTMLResponse)
async def home() -> str:
    return render_page("Home", HOME_BODY, extra_head=home_json_ld())


@router.get("/product", response_class=HTMLResponse)
async def product() -> str:
    return render_page("Product", PRODUCT_BODY)


@router.get("/pricing", response_class=HTMLResponse)
async def pricing() -> str:
    return render_page("Pricing", PRICING_BODY)


@router.get("/contact", response_class=HTMLResponse)
async def contact() -> str:
    return render_page("Contact", CONTACT_BODY)


@router.get("/blog", response_class=HTMLResponse)
async def blog_index() -> str:
    return render_page("Blog", blog_index_body())


@router.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(slug: str) -> str:
    build_body = BLOG_POSTS.get(slug)
    if build_body is None:
        raise HTTPException(status_code=404)
    return render_page("Blog", build_body())


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    lines = ["User-agent: *", "Disallow: /search-cache/"]
    if is_variant_active(DYNAMIC_LINK_GRAPH_TRAP.variant_id):
        lines.append(f"Disallow: {DYNAMIC_GRAPH_BASE_PATH}/")
    lines.append("Sitemap: /sitemap.xml")
    return "\n".join(lines) + "\n"


@router.get("/sitemap.xml")
async def sitemap_xml() -> Response:
    urls = "".join(f"<url><loc>{path}</loc></url>" for path in _LEGIT_PATHS)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(content=xml, media_type="application/xml")