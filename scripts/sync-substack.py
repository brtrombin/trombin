#!/usr/bin/env python3
"""
sync-substack.py
Lê o RSS do Substack e cria articles/*.md + img/*.jpg para posts novos.
Rodado pelo GitHub Actions diariamente.
"""

import os
import re
import sys
import textwrap
from pathlib import Path
from datetime import datetime, timezone

import feedparser
import html2text
import requests
from PIL import Image
from io import BytesIO

# ── Configuração ────────────────────────────────────────────────────────────
RSS_URL        = "https://naocabe.substack.com/feed"
ARTICLES_DIR   = Path("articles")
IMG_DIR        = Path("img")
MAX_WIDTH      = 1920
JPEG_QUALITY   = 75
LEAD_MAX_CHARS = 180


def slug_from_url(url: str) -> str:
    match = re.search(r"/p/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Não foi possível extrair slug de: {url}")
    return match.group(1)


def article_exists(slug: str) -> bool:
    return (ARTICLES_DIR / f"{slug}.md").exists()


def fetch_image(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        img.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True
    except Exception as e:
        print(f"  aviso: falha ao baixar imagem {url}: {e}")
        return False


def get_enclosure_url(entry) -> str:
    if hasattr(entry, "enclosures") and entry.enclosures:
        enc = entry.enclosures[0]
        if enc.get("type", "").startswith("image/"):
            return enc.get("href", "")

    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url", "")

    content = ""
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        content = entry.summary or ""

    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)

    return ""


def html_to_markdown(html: str) -> str:
    html = re.sub(r"<figure[^>]*>.*?</figure>", "", html, flags=re.DOTALL)
    html = re.sub(r"<img[^>]*>", "", html)

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    h.unicode_snob = True
    h.wrap_links = False
    return h.handle(html).strip()


def extract_lead(entry) -> str:
    raw = getattr(entry, "summary", "") or ""
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > LEAD_MAX_CHARS:
        clean = clean[:LEAD_MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return clean


def build_front_matter(slug: str, entry, hero_image: str) -> str:
    date_str = ""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    title = entry.get("title", slug).replace('"', '\\"')
    lead  = extract_lead(entry).replace('"', '\\"')
    link  = entry.get("link", "")

    hero_line = f'"/img/{slug}.jpg"' if hero_image else '""'

    return textwrap.dedent(f"""\
        ---
        draft: false
        title: "{title}"
        date: {date_str}
        type: leitura
        lead: "{lead}"
        substack_url: "{link}"
        location: ""
        hero_image: {hero_line}
        camera: ""
        film: ""
        aperture: ""
        speed: ""
        author_note: ""
        themes: []
        ---
        """)


def sync():
    ARTICLES_DIR.mkdir(exist_ok=True)
    IMG_DIR.mkdir(exist_ok=True)

    print(f"Lendo feed: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)

    if feed.bozo:
        print(f"aviso: problema no feed: {feed.bozo_exception}")

    entries = feed.entries
    print(f"Posts no feed: {len(entries)}")

    new_count = 0
    for entry in entries:
        try:
            link = entry.get("link", "")
            if not link:
                continue

            slug = slug_from_url(link)

            if article_exists(slug):
                print(f"  [skip] {slug}")
                continue

            print(f"  [new]  {slug}")

            img_url = get_enclosure_url(entry)
            hero_image = ""
            if img_url:
                dest_img = IMG_DIR / f"{slug}.jpg"
                if fetch_image(img_url, dest_img):
                    hero_image = f"/img/{slug}.jpg"
                    print(f"         imagem -> {dest_img}")

            body_html = ""
            if hasattr(entry, "content") and entry.content:
                body_html = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                body_html = entry.summary or ""

            body_md = html_to_markdown(body_html)

            fm   = build_front_matter(slug, entry, hero_image)
            dest = ARTICLES_DIR / f"{slug}.md"
            dest.write_text(fm + "\n" + body_md + "\n", encoding="utf-8")
            print(f"         artigo -> {dest}")
            new_count += 1

        except Exception as e:
            print(f"  erro processando entry: {e}")
            continue

    print(f"\nPronto: {new_count} novo(s) post(s).")
    return new_count


if __name__ == "__main__":
    sync()
    sys.exit(0)
