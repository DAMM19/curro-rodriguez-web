#!/usr/bin/env python3
"""
update_diario.py
Comprueba si Curro Rodríguez ha publicado una nueva columna
en Tribuna de Andalucía y la añade al Diario del CEO en index.html.
"""

import re
import json
import sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError
from html import unescape

try:
    from html.parser import HTMLParser
except ImportError:
    from HTMLParser import HTMLParser

HTML_PATH = 'index.html'

AUTHOR_URL = 'https://www.tribunadeandalucia.es/author/curro-rodriguez/'
SEARCH_URL = 'https://www.tribunadeandalucia.es/?s=curro+rodriguez'

MESES = {
    'enero': 'Ene', 'febrero': 'Feb', 'marzo': 'Mar', 'abril': 'Abr',
    'mayo': 'May', 'junio': 'Jun', 'julio': 'Jul', 'agosto': 'Ago',
    'septiembre': 'Sep', 'octubre': 'Oct', 'noviembre': 'Nov', 'diciembre': 'Dic',
    'january': 'Ene', 'february': 'Feb', 'march': 'Mar', 'april': 'Abr',
    'may': 'May', 'june': 'Jun', 'july': 'Jul', 'august': 'Ago',
    'september': 'Sep', 'october': 'Oct', 'november': 'Nov', 'december': 'Dic',
}


def fetch_url(url):
    """Fetches a URL and returns HTML content."""
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; diariobot/1.0)',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'es-ES,es;q=0.9',
    })
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except URLError as e:
        print(f"  Error fetching {url}: {e}")
        return None


def parse_tribuna_articles(html):
    """Extracts articles from Tribuna de Andalucía HTML."""
    articles = []

    # Find article blocks using regex (no external deps needed)
    # Look for <article> or entry patterns
    article_pattern = re.compile(
        r'<article[^>]*>(.*?)</article>',
        re.DOTALL | re.IGNORECASE
    )
    title_pattern = re.compile(
        r'<h[23][^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )
    date_pattern = re.compile(
        r'<time[^>]*datetime="([^"]*)"[^>]*>([^<]*)</time>',
        re.IGNORECASE
    )
    excerpt_pattern = re.compile(
        r'<div[^>]*class="[^"]*entry-summary[^"]*"[^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE
    )

    for article_match in article_pattern.finditer(html):
        article_html = article_match.group(1)

        title_match = title_pattern.search(article_html)
        if not title_match:
            continue

        url = title_match.group(1).strip()
        title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
        title = unescape(title)

        # Skip if not about opinion/columna
        if not url or 'tribunadeandalucia.es' not in url:
            continue

        # Get date
        fecha = ''
        fecha_iso = ''
        date_match = date_pattern.search(article_html)
        if date_match:
            fecha_iso = date_match.group(1)[:10]
            date_text = date_match.group(2).lower().strip()
            # Try to format: "27 de marzo de 2026" -> "Mar 2026"
            parts = date_text.replace(' de ', ' ').split()
            for i, part in enumerate(parts):
                if part in MESES and i + 1 < len(parts):
                    year = parts[i + 1] if parts[i + 1].isdigit() else ''
                    fecha = f"{MESES[part]} {year}".strip()
                    break
            if not fecha and fecha_iso:
                try:
                    dt = datetime.strptime(fecha_iso, '%Y-%m-%d')
                    meses_num = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
                    fecha = f"{meses_num[dt.month-1]} {dt.year}"
                except Exception:
                    pass

        # Get excerpt
        excerpt = ''
        exc_match = excerpt_pattern.search(article_html)
        if exc_match:
            excerpt = re.sub(r'<[^>]+>', '', exc_match.group(1)).strip()
            excerpt = unescape(excerpt)[:300]

        if title and url:
            articles.append({
                'url': url,
                'title': title,
                'date': fecha,
                'date_iso': fecha_iso,
                'excerpt': excerpt,
            })

    return articles


def extract_diario_array(html):
    """Extracts the DIARIO JS array from the HTML."""
    match = re.search(r'var DIARIO=(\[.*?\]);', html, re.DOTALL)
    if not match:
        raise ValueError("No se encontró el array DIARIO en el HTML")
    return json.loads(match.group(1))


def build_diario_array(html, items):
    """Replaces the DIARIO array in the HTML."""
    json_str = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    return re.sub(r'var DIARIO=\[.*?\];', f'var DIARIO={json_str};', html, flags=re.DOTALL)


def article_to_diario_item(article):
    """Converts a scraped article to DIARIO array format."""
    # Generate dt (display date) from date
    dt = article.get('date', '')
    return {
        't': article['title'],
        'd': article.get('date_iso', '') or datetime.now().strftime('%Y-%m-%d'),
        'dt': dt,
        'i': 'https://www.tribunadeandalucia.es/wp-content/uploads/2025/07/WhatsApp-Image-2025-07-07-at-17.16.00-e1755524947319.jpeg',
        'u': article['url'],
        'e': article.get('excerpt', article['title'])
    }


def main():
    print("=== Actualización Diario del CEO — Tribuna de Andalucía ===")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Read current HTML
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    current_diario = extract_diario_array(html)
    current_urls = {item['u'] for item in current_diario}
    print(f"Artículos actuales en Diario del CEO: {len(current_diario)}")

    # Try author page first, then search
    new_articles = []
    for url in [AUTHOR_URL, SEARCH_URL]:
        print(f"Scrapeando: {url}")
        page_html = fetch_url(url)
        if page_html:
            articles = parse_tribuna_articles(page_html)
            print(f"  Artículos encontrados: {len(articles)}")
            for a in articles:
                if a['url'] not in current_urls and a['url'] not in [x['url'] for x in new_articles]:
                    new_articles.append(a)

    if not new_articles:
        print("No hay columnas nuevas. No se realizan cambios.")
        sys.exit(0)

    print(f"Columnas nuevas encontradas: {len(new_articles)}")

    # Sort by date (newest first) and add to beginning of DIARIO
    new_items = [article_to_diario_item(a) for a in new_articles]
    updated_diario = new_items + current_diario

    # Sort all by date descending
    def sort_key(item):
        d = item.get('d', '')
        return d if d else '0000-00-00'

    updated_diario.sort(key=sort_key, reverse=True)

    print(f"Total artículos tras actualización: {len(updated_diario)}")

    # Update HTML
    updated_html = build_diario_array(html, updated_diario)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(updated_html)

    print(f"✅ index.html actualizado con {len(new_items)} columna(s) nueva(s).")
    for a in new_articles:
        print(f"   + {a['date']} — {a['title']}")


if __name__ == '__main__':
    main()
