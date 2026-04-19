"""In-app Help Center — markdown article serving + search.

Articles live in `backend/help_content/`, indexed by `_index.json`.
Public read-only endpoints (require auth, but tenant-agnostic).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/help", tags=["help"])

CONTENT_DIR = Path(__file__).parent.parent / "help_content"
INDEX_PATH = CONTENT_DIR / "_index.json"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,80}$")


def _load_index() -> dict[str, Any]:
    if not INDEX_PATH.exists():
        return {"categories": []}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def _all_articles() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cat in _load_index().get("categories", []):
        for art in cat.get("articles", []):
            out.append({**art, "category_key": cat["key"],
                        "category_title": cat["title"]})
    return out


def _read_article(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise HTTPException(400, "Geçersiz slug")
    p = CONTENT_DIR / f"{slug}.md"
    # Defensive: ensure we never escape CONTENT_DIR even with valid slug.
    try:
        p.resolve().relative_to(CONTENT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(400, "Geçersiz slug") from exc
    if not p.exists():
        raise HTTPException(404, "Makale bulunamadı")
    return p.read_text(encoding="utf-8")


@router.get("/index")
async def get_index(_: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return full category tree with article titles."""
    return _load_index()


@router.get("/articles/{slug}")
async def get_article(
    slug: str,
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    body = _read_article(slug)
    # Lookup metadata from index.
    meta = next((a for a in _all_articles() if a.get("slug") == slug), None)
    if not meta:
        raise HTTPException(404, "Makale meta bilgisi yok")
    return {
        "slug": slug,
        "title": meta.get("title"),
        "category_key": meta.get("category_key"),
        "category_title": meta.get("category_title"),
        "tags": meta.get("tags", []),
        "body_markdown": body,
    }


@router.get("/search")
async def search_articles(
    q: str,
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Naive case-insensitive substring search over title+body."""
    needle = (q or "").strip().lower()
    if len(needle) < 2:
        return {"query": q, "count": 0, "items": []}
    hits: list[dict[str, Any]] = []
    for art in _all_articles():
        slug = art.get("slug", "")
        try:
            body = _read_article(slug).lower()
        except HTTPException:
            continue
        title = (art.get("title") or "").lower()
        tags = " ".join(art.get("tags", [])).lower()
        if needle in title or needle in body or needle in tags:
            # Build small snippet around first body match.
            idx = body.find(needle)
            snippet = ""
            if idx >= 0:
                start = max(0, idx - 60)
                end = min(len(body), idx + len(needle) + 80)
                snippet = "…" + body[start:end].replace("\n", " ") + "…"
            hits.append({
                "slug": slug,
                "title": art.get("title"),
                "category_title": art.get("category_title"),
                "snippet": snippet,
                "score": (3 if needle in title else 1),
            })
    hits.sort(key=lambda h: -h["score"])
    return {"query": q, "count": len(hits), "items": hits[:25]}
