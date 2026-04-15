#!/usr/bin/env python3
"""
update_actualidad.py
Busca noticias nuevas sobre Curro Rodríguez en Google News RSS
y actualiza la sección Actualidad del index.html.
Mantiene un máximo de 15 noticias, nuevas arriba, antiguas abajo.
"""

import re
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError
from html import unescape

MAX_NOTICIAS = 15

BUSQUEDAS = [
    '"Curro Rodríguez" empresario',
    '"Ly Company" Curro',
    '"El Aprendedor" Curro Rodríguez',
    '"Aqualy" Curro Rodríguez',
]

MEDIOS_POSITIVOS = [
    'euronews', 'financial times', 'el economista', 'expansion', 'cinco dias',
    'el pais', 'el mundo', 'abc', 'la vanguardia', 'el confidencial',
    'tribuna de andalucia', 'andalucia economica', 'malaga hoy', 'sur',
    'ico.es', 'junta', 'gobierno', 'reuters', 'bloomberg', 'forbes'
]

PALABRAS_NEGATIVAS = [
    'fraude', 'estafa', 'detenido', 'condena', 'multa', 'demanda', 'escandalo',
    'investigado', 'acusado', 'polemic', 'critica', 'fracas'
]

HTML_PATH = 'index.html'


def fetch_rss(query):
    """Fetches Google News RSS for a given query."""
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=es&gl=ES&ceid=ES:es"
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; newsbot/1.0)'})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read()
    except URLError as e:
        print(f"  Error fetching RSS for '{query}': {e}")
        return None


def parse_rss(xml_data):
    """Parses RSS XML and returns list of articles."""
    articles = []
    try:
        root = ET.fromstring(xml_data)
        channel = root.find('channel')
        if not channel:
            return articles
        for item in channel.findall('item'):
            title = item.findtext('title', '').strip()
            link = item.findtext('link', '').strip()
            pub_date = item.findtext('pubDate', '').strip()
            source_el = item.find('source')
            source = source_el.text.strip() if source_el is not None else ''

            # Parse date
            fecha = ''
            try:
                dt = datetime.strptime(pub_date[:25], '%a, %d %b %Y %H:%M:%S')
                meses = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
                fecha = f"{meses[dt.month-1]} {dt.year}"
            except Exception:
                fecha = pub_date[:7] if pub_date else ''

            if title and link:
                articles.append({
                    'title': unescape(title),
                    'url': link,
                    'source': source,
                    'date': fecha,
                    'pub_date': pub_date,
                })
    except ET.ParseError as e:
        print(f"  XML parse error: {e}")
    return articles


def score_article(article):
    """Returns a relevance score. Returns -1 if article should be discarded."""
    title_lower = article['title'].lower()
    source_lower = article['source'].lower()

    # Discard negative content
    for word in PALABRAS_NEGATIVAS:
        if word in title_lower:
            return -1

    # Must mention Curro or related brand
    keywords = ['curro', 'ly company', 'aprendedor', 'aqualy', 'hispacaribe']
    if not any(k in title_lower for k in keywords):
        return -1

    score = 50  # base score
    for medio in MEDIOS_POSITIVOS:
        if medio in source_lower:
            score += 30
            break

    return score


def extract_news_array(html):
    """Extracts the NEWS JS array from the HTML."""
    match = re.search(r'var NEWS=(\[.*?\]);', html, re.DOTALL)
    if not match:
        raise ValueError("No se encontró el array NEWS en el HTML")
    return json.loads(match.group(1))


def build_news_array(html, new_items):
    """Replaces the NEWS array in the HTML with the updated one."""
    json_str = json.dumps(new_items, ensure_ascii=False, separators=(',', ':'))
    return re.sub(r'var NEWS=\[.*?\];', f'var NEWS={json_str};', html, flags=re.DOTALL)


def articles_to_news_items(articles):
    """Converts RSS articles to NEWS array format."""
    items = []
    for a in articles:
        items.append({
            'u': a['url'],
            's': a['source'],
            'd': a['date'],
            't': a['title'],
            'e': f"Noticia publicada en {a['source']}. Haz clic para leer el artículo completo."
        })
    return items


def main():
    print("=== Actualización Actualidad Curro Rodríguez ===")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Read current HTML
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    current_news = extract_news_array(html)
    current_urls = {item['u'] for item in current_news}
    print(f"Noticias actuales: {len(current_news)}")

    # Fetch new articles
    all_articles = []
    for query in BUSQUEDAS:
        print(f"Buscando: {query}")
        xml_data = fetch_rss(query)
        if xml_data:
            articles = parse_rss(xml_data)
            print(f"  Encontrados: {len(articles)} artículos")
            all_articles.extend(articles)

    # Deduplicate by URL
    seen_urls = set()
    unique_articles = []
    for a in all_articles:
        if a['url'] not in seen_urls:
            seen_urls.add(a['url'])
            unique_articles.append(a)

    # Score and filter
    valid_articles = []
    for a in unique_articles:
        if a['url'] in current_urls:
            continue  # Already in the list
        score = score_article(a)
        if score >= 0:
            a['score'] = score
            valid_articles.append(a)

    # Sort by score
    valid_articles.sort(key=lambda x: x.get('score', 0), reverse=True)

    print(f"Artículos nuevos válidos: {len(valid_articles)}")

    if not valid_articles:
        print("No hay noticias nuevas. No se realizan cambios.")
        sys.exit(0)

    # Convert new articles and prepend to current list
    new_items = articles_to_news_items(valid_articles[:5])  # Max 5 new per run
    updated_news = new_items + current_news

    # Trim to MAX_NOTICIAS
    if len(updated_news) > MAX_NOTICIAS:
        updated_news = updated_news[:MAX_NOTICIAS]
        print(f"Lista recortada a {MAX_NOTICIAS} noticias")

    print(f"Total noticias tras actualización: {len(updated_news)}")

    # Update HTML
    updated_html = build_news_array(html, updated_news)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(updated_html)

    print(f"✅ index.html actualizado con {len(new_items)} noticias nuevas.")


if __name__ == '__main__':
    main()
