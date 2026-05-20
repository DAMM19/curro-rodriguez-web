#!/usr/bin/env python3
"""
update_diario.py
Comprueba si Curro Rodríguez ha publicado una nueva columna en Tribuna de Andalucía
y actualiza el array DIARIO del index.html.

El listado de autor no trae fecha por artículo, así que para cada columna NUEVA
se visita su propia página y se leen las etiquetas meta (article:published_time,
og:image, og:description) para rellenar fecha, imagen y resumen correctos.
"""
import re
import json
import sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html import unescape

# ── Configuración ──────────────────────────────────────────────────────────────
AUTHOR_URL = 'https://www.tribunadeandalucia.es/nueva-economia/curro-rodriguez/'
HTML_PATH  = 'index.html'

# Imagen por defecto si un artículo no tuviera og:image
DEFAULT_IMG = 'https://www.tribunadeandalucia.es/wp-content/uploads/2025/07/WhatsApp-Image-2025-07-07-at-17.16.00-e1755524947319.jpg'

MESES_NUM = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

# ── Helpers de red ──────────────────────────────────────────────────────────────
def fetch_url(url, fatal=True):
    """Descarga una URL y devuelve el HTML.

    Con fatal=True (por defecto) aborta el workflow con sys.exit(1) ante cualquier
    fallo, para que la ejecución salga en ROJO y nos enteremos en vez de pasar
    como "success" sin hacer nada. Con fatal=False devuelve None (se usa al
    enriquecer artículos: si una página falla, seguimos con valores por defecto).
    """
    req = Request(url, headers={
        # User-Agent realista de navegador. Tribuna (Cloudflare) devuelve 403
        # al UA "diariobot/1.0" y deja pasar a un Chrome normal.
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,'
            'image/avif,image/webp,*/*;q=0.8'
        ),
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    })
    try:
        with urlopen(req, timeout=20) as resp:
            status = getattr(resp, 'status', 200)
            if status != 200:
                print(f"  ❌ Respuesta HTTP {status} al pedir {url}")
                if fatal:
                    sys.exit(1)
                return None
            return resp.read().decode('utf-8', errors='replace')
    except HTTPError as e:
        print(f"  ❌ HTTPError {e.code} al pedir {url}: {e.reason}")
        if fatal:
            sys.exit(1)
        return None
    except URLError as e:
        print(f"  ❌ URLError al pedir {url}: {e.reason}")
        if fatal:
            sys.exit(1)
        return None
    except Exception as e:
        print(f"  ❌ Excepción inesperada al pedir {url}: {e}")
        if fatal:
            sys.exit(1)
        return None

def meta_content(html, prop):
    """Devuelve el content de una etiqueta <meta property|name="prop" ...>,
    soportando los dos órdenes de atributos (property antes o después de content)."""
    p = re.escape(prop)
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']' + p + r'["\'][^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE)
    if m:
        return unescape(m.group(1).strip())
    m = re.search(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']' + p + r'["\']',
        html, re.IGNORECASE)
    if m:
        return unescape(m.group(1).strip())
    return ''

# ── Parseo del listado ──────────────────────────────────────────────────────────
def parse_tribuna_articles(html):
    """Extrae (url, titulo) del listado de autor de Tribuna.
    Usa la estructura <h2 class='entry-title'><a href=...>...</a></h2>.
    """
    articles = []
    seen = set()
    title_pattern = re.compile(
        r'<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE
    )
    for m in title_pattern.finditer(html):
        url = m.group(1).strip()
        title = unescape(re.sub(r'<[^>]+>', '', m.group(2)).strip())
        if not url or 'tribunadeandalucia.es' not in url or url in seen:
            continue
        seen.add(url)
        articles.append({'url': url, 'title': title})
    return articles

# ── Enriquecer cada artículo nuevo con datos de su propia página ─────────────────
def enrich_article(article):
    """Visita la página del artículo y rellena fecha, imagen y resumen."""
    article.setdefault('date_iso', '')
    article.setdefault('date', '')
    article.setdefault('image', DEFAULT_IMG)
    article.setdefault('excerpt', article['title'])

    html = fetch_url(article['url'], fatal=False)
    if not html:
        print(f"  ⚠️  No se pudo abrir {article['url']}, uso valores por defecto.")
        return article

    pub = meta_content(html, 'article:published_time')   # 2026-05-20T14:58:38+02:00
    if pub:
        article['date_iso'] = pub[:10]
        try:
            d = datetime.strptime(article['date_iso'], '%Y-%m-%d')
            article['date'] = f"{MESES_NUM[d.month-1]} {d.year}"
        except Exception:
            pass

    img = meta_content(html, 'og:image')
    if img:
        article['image'] = img

    desc = meta_content(html, 'og:description') or meta_content(html, 'description')
    if desc:
        article['excerpt'] = desc

    return article

# ── Manejo del array DIARIO en el HTML ───────────────────────────────────────────
def extract_diario_array(html):
    match = re.search(r'var DIARIO=(\[.*?\]);', html, re.DOTALL)
    if not match:
        raise ValueError("No se encontró el array DIARIO en el HTML")
    raw = match.group(1)
    raw = re.sub(r'(?<=[{,])(\w+)(?=:)', r'"\1"', raw)  # claves JS -> JSON
    return json.loads(raw)

def build_diario_array(html, items):
    json_str = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    return re.sub(r'var DIARIO=\[.*?\];', f'var DIARIO={json_str};', html, flags=re.DOTALL)

def article_to_diario_item(article):
    return {
        't':  article['title'],
        'd':  article.get('date_iso', '') or datetime.now().strftime('%Y-%m-%d'),
        'dt': article.get('date', ''),
        'i':  article.get('image', DEFAULT_IMG),
        'u':  article['url'],
        'e':  article.get('excerpt', article['title']),
    }

def sort_key(item):
    d = item.get('d', '')
    return d if d else '0000-00-00'

# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    print("=== Actualización Diario del CEO — Tribuna de Andalucía ===")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    current_diario = extract_diario_array(html)
    current_urls = {item['u'] for item in current_diario}
    print(f"Artículos actuales en Diario del CEO: {len(current_diario)}")

    print(f"Scrapeando: {AUTHOR_URL}")
    page_html = fetch_url(AUTHOR_URL)            # fatal=True: aborta en rojo si falla
    found = parse_tribuna_articles(page_html)
    print(f"  Artículos encontrados en el listado: {len(found)}")

    if len(found) == 0:
        print("❌ El parser no encontró ningún artículo. La página pudo cambiar o estar bloqueada.")
        sys.exit(1)

    new_articles = [a for a in found if a['url'] not in current_urls]

    if not new_articles:
        print("No hay columnas nuevas. No se realizan cambios.")
        sys.exit(0)

    print(f"Columnas nuevas encontradas: {len(new_articles)}")
    for a in new_articles:
        enrich_article(a)
        print(f"  + [{a.get('date') or '¿sin fecha?'}] {a['title']}")

    new_items = [article_to_diario_item(a) for a in new_articles]
    updated_diario = new_items + current_diario
    updated_diario.sort(key=sort_key, reverse=True)

    print(f"Total artículos tras actualización: {len(updated_diario)}")

    updated_html = build_diario_array(html, updated_diario)
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(updated_html)

    print(f"✅ index.html actualizado con {len(new_items)} columna(s) nueva(s).")

if __name__ == '__main__':
    main()
