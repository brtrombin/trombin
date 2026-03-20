#!/usr/bin/env python3
"""
Sync Substack RSS → Eleventy articles.

Para cada entrada do RSS:
  - Extrai o slug da URL (/p/SLUG)
  - Pula se articles/SLUG.md já existir
  - Converte o HTML (content:encoded) para Markdown
  - Baixa e comprime a imagem da enclosure → img/SLUG.jpg
  - Escreve articles/SLUG.md com front matter completo
"""

from __future__ import annotations

import re
import sys
import textwrap
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import html2text
import requests
from PIL import Image

# ── Config ───────────────────────────────────────────────────────────────────
FEED_URL    = "https://naocabe.substack.com/feed"
REPO_ROOT   = Path(__file__).resolve().parent.parent
ARTICLES_DIR = REPO_ROOT / "articles"
IMG_DIR     = REPO_ROOT / "img"
IMG_MAX_WIDTH = 1920
IMG_QUALITY   = 75
# ─────────────────────────────────────────────────────────────────────────────


def slug_from_url(url: str) -> str | None:
    """Extrai o slug de URLs como https://naocabe.substack.com/p/meu-slug."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "p":
        return parts[1]
    return None


def load_existing_urls() -> set[str]:
    """Retorna todos os substack_url já presentes nos .md existentes."""
    urls: set[str] = set()
    for md in ARTICLES_DIR.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        m = re.search(r'^substack_url:\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            urls.add(m.group(1).rstrip("/"))
    return urls


def article_exists(slug: str) -> bool:
    """Checa se slug.md existe OU se algum .md existente começa com o mesmo slug
    (ex: 'delirio-de-uma-mente' cobre 'delirio-de-uma-mente-sem-sono-em-roma')."""
    if (ARTICLES_DIR / f"{slug}.md").exists():
        return True
    # Prefixo: o slug do RSS é substring do início de algum arquivo existente
    for md in ARTICLES_DIR.glob("*.md"):
        if md.stem.startswith(slug):
            return True
    return False


IMG_MIN_WIDTH = 400  # imagens menores que isso são ícones/placeholders — ignorar

def fetch_image(url: str, dest: Path) -> bool:
    """Baixa a imagem, redimensiona para max 1920px e salva como JPEG q75.
    Retorna False se a imagem for menor que IMG_MIN_WIDTH (placeholder)."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")

        if img.width < IMG_MIN_WIDTH:
            print(f"    [img] ignorado {dest.name} — muito pequeno ({img.width}x{img.height})")
            return False

        if img.width > IMG_MAX_WIDTH:
            ratio = IMG_MAX_WIDTH / img.width
            img = img.resize(
                (IMG_MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS
            )
        img.save(dest, "JPEG", quality=IMG_QUALITY, optimize=True)
        print(f"    [img] salvo {dest.name} ({img.width}x{img.height})")
        return True
    except Exception as exc:
        print(f"    [img] FALHOU ao baixar {url}: {exc}", file=sys.stderr)
        return False


def html_to_markdown(html: str, hero_url: str | None = None) -> str:
    """Converte HTML para Markdown, preservando imagens inline do corpo.

    Se `hero_url` for passado, remove apenas a primeira figura que contenha
    essa URL (para evitar duplicar a hero_image já exibida no topo da página).
    """
    # Remove call-to-action de assinatura do Substack
    html = re.sub(
        r"<div[^>]*subscription-widget[^>]*>.*?</div>",
        "", html, flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove apenas a figura que contém a hero image (se fornecida)
    if hero_url:
        escaped = re.escape(hero_url.split("?")[0])  # ignora query string
        html = re.sub(
            r"<figure[^>]*>(?:(?!<figure).)*?" + escaped + r".*?</figure>",
            "", html, count=1, flags=re.IGNORECASE | re.DOTALL,
        )

    h = html2text.HTML2Text()
    h.ignore_links   = False
    h.ignore_images  = False  # mantém imagens inline como ![alt](url)
    h.body_width     = 0      # sem quebra de linha forçada
    h.unicode_snob   = True
    h.protect_links  = True
    h.wrap_links     = False

    md = h.handle(html)
    md = re.sub(r"\n{3,}", "\n\n", md)  # colapsa linhas em branco extras
    return md.strip()


def extract_lead(entry) -> str:
    """Extrai o primeiro parágrafo/descrição como lead (~160 chars)."""
    raw = getattr(entry, "summary", "") or ""
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > 160:
        clean = clean[:157].rsplit(" ", 1)[0] + "..."
    return clean


def get_enclosure_url(entry) -> str | None:
    """Retorna a URL da imagem destacada (enclosure ou media_thumbnail)."""
    if hasattr(entry, "enclosures") and entry.enclosures:
        enc = entry.enclosures[0]
        href = enc.get("href") or enc.get("url", "")
        if href and enc.get("type", "").startswith("image/"):
            return href
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")
    return None


def get_html_body(entry) -> str:
    """Retorna o HTML completo do post (content:encoded, fallback: summary)."""
    if hasattr(entry, "content") and entry.content:
        for block in entry.content:
            if block.get("type") in ("text/html", "application/xhtml+xml"):
                return block.value
    return getattr(entry, "summary", "")


def parse_date(entry) -> str:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return date(*entry.published_parsed[:3]).isoformat()
    return date.today().isoformat()


def build_front_matter(slug: str, entry, has_image: bool) -> str:
    title      = entry.get("title", "").replace('"', '\\"')
    pub_date   = parse_date(entry)
    lead       = extract_lead(entry).replace('"', '\\"')
    substack_url = entry.get("link", "")
    hero_image = f"/img/{slug}.jpg" if has_image else ""

    return textwrap.dedent(f"""\
        ---
        draft: false
        title: "{title}"
        date: {pub_date}
        type: leitura
        lead: "{lead}"
        substack_url: "{substack_url}"
        location: ""
        hero_image: "{hero_image}"
        camera: ""
        film: ""
        aperture: ""
        speed: ""
        author_note: ""
        themes: []
        ---
        """)


def sync():
    print(f"Buscando feed: {FEED_URL}")
    feed = feedparser.parse(FEED_URL)

    if feed.bozo and not feed.entries:
        print(f"ERRO: não foi possível parsear o feed: {feed.bozo_exception}", file=sys.stderr)
        sys.exit(1)

    new_count = 0
    existing_urls = load_existing_urls()

    for entry in feed.entries:
        url  = entry.get("link", "").rstrip("/")
        slug = slug_from_url(url)

        if not slug:
            print(f"  [skip] sem slug em: {url}")
            continue

        if article_exists(slug):
            print(f"  [skip] {slug}.md já existe")
            continue

        if url in existing_urls:
            print(f"  [skip] {slug} já existe com outro nome (URL duplicada)")
            continue

        print(f"  [novo] {slug}")

        # Imagem
        img_url   = get_enclosure_url(entry)
        has_image = False
        if img_url:
            has_image = fetch_image(img_url, IMG_DIR / f"{slug}.jpg")
        else:
            print(f"    [img] sem enclosure para {slug}")

        # Conteúdo (passa hero_url para evitar duplicar a imagem de capa)
        html_body = get_html_body(entry)
        md_body   = html_to_markdown(html_body, hero_url=img_url) if html_body else ""

        # Escreve o .md
        md_path = ARTICLES_DIR / f"{slug}.md"
        md_path.write_text(
            build_front_matter(slug, entry, has_image) + "\n" + md_body + "\n",
            encoding="utf-8",
        )
        print(f"    [md]  escrito {md_path.name}")
        new_count += 1

    print(f"\nConcluído. {new_count} artigo(s) novo(s) criado(s).")


if __name__ == "__main__":
    sync()
