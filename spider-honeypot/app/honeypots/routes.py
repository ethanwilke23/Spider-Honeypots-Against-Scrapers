"""
Routes for the legitimate decoy site pages, robots.txt and sitemap.xml.

robots.txt has two Disallow entries: /search-cache/, which leads nowhere,
and the dynamic-graph trap path. The sitemap lists only legitimate pages;
honeypot paths are never included.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.honeypots.routes import DYNAMIC_GRAPH_BASE_PATH
from app.site.content import (
    BLOG_INDEX_BODY,
    BLOG_POSTS,
    CONTACT_BODY,
    HOME_BODY,
    HOME_JSON_LD,
    PRICING_BODY,
    PRODUCT_BODY,
)
from app.site.layout import render_page

router = APIRouter()

_LEGIT_PATHS = ["/", "/product", "/pricing", "/blog", "/contact"] + [
    f"/blog/{slug}" for slug in BLOG_POSTS
]


@router.get("/", response_class=HTMLResponse)
async def home() -> str:
    return render_page("Home", HOME_BODY, extra_head=HOME_JSON_LD)


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
    return render_page("Blog", BLOG_INDEX_BODY)


@router.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(slug: str) -> str:
    body = BLOG_POSTS.get(slug)
    if body is None:
        raise HTTPException(status_code=404)
    return render_page("Blog", body)


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Disallow: /search-cache/\n"
        f"Disallow: {DYNAMIC_GRAPH_BASE_PATH}/\n"
        "Sitemap: /sitemap.xml\n"
    )


@router.get("/sitemap.xml")
async def sitemap_xml() -> Response:
    urls = "".join(f"<url><loc>{path}</loc></url>" for path in _LEGIT_PATHS)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(content=xml, media_type="application/xml")