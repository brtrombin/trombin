#!/usr/bin/env python3
"""
sync-substack.py
Lê o RSS do Substack e cria articles/*.md + img/*.jpg para posts novos.
Rodado pelo GitHub Actions diariamente (.github/workflows/sync-substack.yml).

Fluxo, para cada post do feed:
  1. extrai o slug da URL (/p/<slug>) — ele vira o nome do .md e da imagem
  2. se articles/<slug>.md já existe, pula (nunca sobrescreve edições manuais)
  3. baixa a imagem de capa, reduz e salva em img/<slug>.jpg
  4. converte o HTML do post em markdown
  5. grava o .md com o front matter que os layouts do site esperam

Uso local: pip install -r requirements-sync.txt && python scripts/sync-substack.py
"""

import html
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
ARTICLES_DIR   = Path("articles")   # relativo à raiz do repositório
IMG_DIR        = Path("img")
MAX_WIDTH      = 1920               # largura máxima da capa, em px
JPEG_QUALITY   = 75
LEAD_MAX_CHARS = 180                # tamanho máximo da chamada (lead)


def slug_from_url(url: str) -> str:
    """Extrai o slug de uma URL de post: .../p/meu-texto?x=1 → "meu-texto"."""
    match = re.search(r"/p/([^/?#]+)", url)
    if not match:
        raise ValueError(f"Não foi possível extrair slug de: {url}")
    return match.group(1)


def article_exists(slug: str) -> bool:
    """True se o post já foi importado (existe articles/<slug>.md)."""
    return (ARTICLES_DIR / f"{slug}.md").exists()


def fetch_image(url: str, dest: Path) -> bool:
    """Baixa a imagem, reduz para MAX_WIDTH e salva como JPEG. False se falhar."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        # convert("RGB"): JPEG não aceita transparência (PNG/WebP com alpha)
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
        img.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return True
    except Exception as e:
        # sem capa o post ainda é importado; a home usa um degradê no lugar
        print(f"  aviso: falha ao baixar imagem {url}: {e}")
        return False


def get_enclosure_url(entry) -> str:
    """Encontra a URL da imagem de capa do post, ou "" se não houver.

    Tenta, nesta ordem: enclosure do RSS, media:thumbnail e, por fim,
    a primeira <img> do corpo do post.
    """
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


def html_to_markdown(raw_html: str) -> str:
    """Converte o HTML do post em markdown, descartando as imagens."""
    # remove figuras e imagens antes da conversão: só a capa é aproveitada
    raw_html = re.sub(r"<figure[^>]*>.*?</figure>", "", raw_html, flags=re.DOTALL)
    raw_html = re.sub(r"<img[^>]*>", "", raw_html)

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0  # 0 = não quebra as linhas em largura fixa
    h.unicode_snob = True
    h.wrap_links = False
    # unescape qualquer entity que html2text não tenha convertido
    return html.unescape(h.handle(raw_html).strip())


def extract_lead(entry) -> str:
    """Gera a chamada (lead) a partir do resumo do RSS: texto puro, cortado
    em LEAD_MAX_CHARS sem partir palavra ao meio."""
    raw = getattr(entry, "summary", "") or ""
    clean = re.sub(r"<[^>]+>", "", raw).strip()
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean)
    if len(clean) > LEAD_MAX_CHARS:
        clean = clean[:LEAD_MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return clean


def build_front_matter(slug: str, entry, hero_image: str) -> str:
    """Monta o bloco YAML do topo do .md, com os campos usados pelos layouts.

    Câmera, filme, local e temas ficam vazios para preenchimento manual.
    """
    # data de publicação do post; se o feed não trouxer, usa a data de hoje
    date_str = ""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # aspas duplas escapadas para não quebrar o YAML
    title = html.unescape(entry.get("title", slug)).replace('"', '\\"')
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
    """Importa todos os posts do feed que ainda não existem em articles/."""
    ARTICLES_DIR.mkdir(exist_ok=True)
    IMG_DIR.mkdir(exist_ok=True)

    print(f"Lendo feed: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)

    # bozo = feedparser encontrou XML malformado; segue com o que conseguiu ler
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

            # capa: se o download falhar, hero_image fica vazio
            img_url = get_enclosure_url(entry)
            hero_image = ""
            if img_url:
                dest_img = IMG_DIR / f"{slug}.jpg"
                if fetch_image(img_url, dest_img):
                    hero_image = f"/img/{slug}.jpg"
                    print(f"         imagem -> {dest_img}")

            # corpo: conteúdo completo do post ou, na falta dele, o resumo
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
            # um post com problema não interrompe a importação dos demais
            print(f"  erro processando entry: {e}")
            continue

    print(f"\nPronto: {new_count} novo(s) post(s).")
    return new_count


if __name__ == "__main__":
    sync()
    sys.exit(0)
