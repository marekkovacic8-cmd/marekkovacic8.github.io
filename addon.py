# -*- coding: utf-8 -*-
"""
CSFD scraper modul pro Stream Cinema Caolina
Scrape csfd.cz přímo bez externích závislostí (čistý Python)
"""

import re
import sys
import xbmc

try:
    from urllib.request import urlopen, Request
    from urllib.parse import quote, urlencode
    from urllib.error import URLError
except ImportError:
    from urllib2 import urlopen, Request, URLError
    from urllib import quote, urlencode

CSFD_BASE = 'https://www.csfd.cz'
CSFD_SEARCH = 'https://www.csfd.cz/hledat/?q='

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'cs,sk;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml',
}


def _fetch(url, timeout=10):
    """Stáhne URL a vrátí text."""
    try:
        req = Request(url, headers=HEADERS)
        response = urlopen(req, timeout=timeout)
        raw = response.read()
        # Zkus utf-8, fallback na latin-2
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('iso-8859-2', errors='replace')
    except Exception as e:
        xbmc.log('CSFD scraper fetch error [%s]: %s' % (url, str(e)), xbmc.LOGERROR)
        return ''


def search(query, media_type='movie', limit=20):
    """
    Vyhledá na CSFD a vrátí list výsledků.
    media_type: 'movie' nebo 'tvshow'
    Vrací: [{'id': str, 'title': str, 'year': str, 'rating': str, 'poster': str, 'type': str, 'url': str}]
    """
    try:
        if sys.version_info[0] == 2:
            if isinstance(query, unicode):
                query = query.encode('utf-8')
        encoded = quote(str(query), safe='')
    except Exception:
        encoded = quote(query, safe='')

    url = CSFD_SEARCH + encoded
    html = _fetch(url)
    if not html:
        return []

    results = []

    # Parsování výsledků vyhledávání - filmy/seriály sekce
    # CSFD HTML: <article class="article-poster-60"> ... filmový výsledek
    # Hledáme bloky výsledků
    
    # Nejprve najdeme sekci "Filmy" nebo "Seriály"
    if media_type == 'movie':
        section_pattern = r'<h2[^>]*>\s*Filmy\s*</h2>(.*?)(?:<h2|$)'
    else:
        section_pattern = r'<h2[^>]*>\s*Seriály\s*</h2>(.*?)(?:<h2|$)'

    section_match = re.search(section_pattern, html, re.DOTALL | re.IGNORECASE)
    section_html = section_match.group(1) if section_match else html

    # Parsuj jednotlivé filmy/seriály z výsledků
    # Pattern pro article bloky s filmem
    article_pattern = r'<article[^>]*class="[^"]*article-poster[^"]*"[^>]*>(.*?)</article>'
    articles = re.findall(article_pattern, section_html, re.DOTALL)

    # Fallback - zkus jiný vzor pro novější CSFD design
    if not articles:
        article_pattern2 = r'<li[^>]*class="[^"]*search-item[^"]*"[^>]*>(.*?)</li>'
        articles = re.findall(article_pattern2, section_html, re.DOTALL)

    # Další fallback - hledej přímo linky na filmy
    if not articles:
        results = _parse_search_fallback(section_html, media_type, limit)
        return results

    for article in articles[:limit]:
        item = _parse_article(article, media_type)
        if item:
            results.append(item)

    # Pokud nic, zkus fallback
    if not results:
        results = _parse_search_fallback(section_html, media_type, limit)

    return results


def _parse_article(html, media_type):
    """Parsuje jeden article blok z výsledků hledání."""
    item = {}

    # ID a URL
    url_match = re.search(r'href="(/film/(\d+)[^"]*)"', html)
    if not url_match:
        return None
    item['url'] = CSFD_BASE + url_match.group(1)
    item['id'] = url_match.group(2)

    # Název
    title_match = re.search(r'<h3[^>]*>(.*?)</h3>', html, re.DOTALL)
    if not title_match:
        title_match = re.search(r'<a[^>]*class="[^"]*film[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
    if title_match:
        item['title'] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
    else:
        return None

    # Rok
    year_match = re.search(r'\((\d{4})\)', html)
    item['year'] = year_match.group(1) if year_match else ''

    # Hodnocení
    rating_match = re.search(r'(\d+)\s*%', html)
    item['rating'] = rating_match.group(1) + '%' if rating_match else ''

    # Poster
    poster_match = re.search(r'<img[^>]+src="([^"]+)"[^>]*/>', html)
    if not poster_match:
        poster_match = re.search(r'<img[^>]+src="([^"]+)"', html)
    item['poster'] = poster_match.group(1) if poster_match else ''
    if item['poster'].startswith('//'):
        item['poster'] = 'https:' + item['poster']

    item['type'] = media_type
    return item


def _parse_search_fallback(html, media_type, limit=20):
    """Fallback parser - hledá linky na filmy/seriály přímo v HTML."""
    results = []
    seen_ids = set()

    if media_type == 'movie':
        pattern = r'href="(/film/(\d+)-([^/"]+)/[^"]*)"[^>]*>([^<]+)</a>'
    else:
        pattern = r'href="(/film/(\d+)-([^/"]+)/[^"]*)"[^>]*>([^<]+)</a>'

    matches = re.findall(pattern, html)

    for path, film_id, slug, title in matches:
        if film_id in seen_ids:
            continue
        seen_ids.add(film_id)

        title = title.strip()
        if not title or len(title) < 1:
            continue

        # Filtruj navigační linky
        if any(x in path for x in ['/tvurce/', '/uzivatel/', '/zebricky/', '/magazin/']):
            continue

        results.append({
            'id': film_id,
            'title': title,
            'year': '',
            'rating': '',
            'poster': '',
            'type': media_type,
            'url': CSFD_BASE + path
        })

        if len(results) >= limit:
            break

    return results


def get_movie_details(csfd_id):
    """
    Vrátí detaily filmu z CSFD podle ID.
    Vrací: dict s klíči title, year, rating, poster, plot, genres, directors, actors
    """
    url = '%s/film/%s/' % (CSFD_BASE, csfd_id)
    html = _fetch(url)
    if not html:
        return {}

    details = {'id': csfd_id, 'url': url}

    # Název
    title_match = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', html, re.DOTALL)
    if not title_match:
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    if title_match:
        details['title'] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

    # Rok
    year_match = re.search(r'itemprop="dateCreated"[^>]*>(\d{4})', html)
    if not year_match:
        year_match = re.search(r'\((\d{4})\)', html)
    details['year'] = year_match.group(1) if year_match else ''

    # Hodnocení (procenta)
    rating_match = re.search(r'class="[^"]*film-rating-average[^"]*"[^>]*>(\d+)\s*%', html)
    if not rating_match:
        rating_match = re.search(r'<strong[^>]*>(\d+)\s*%', html)
    if rating_match:
        details['rating'] = int(rating_match.group(1))
        details['rating_str'] = rating_match.group(1) + '%'
    else:
        details['rating'] = 0
        details['rating_str'] = ''

    # Poster
    poster_match = re.search(r'<img[^>]+itemprop="image"[^>]+src="([^"]+)"', html)
    if not poster_match:
        poster_match = re.search(r'class="[^"]*film-poster[^"]*"[^>]*>.*?<img[^>]+src="([^"]+)"', html, re.DOTALL)
    if poster_match:
        details['poster'] = poster_match.group(1)
        if details['poster'].startswith('//'):
            details['poster'] = 'https:' + details['poster']
    else:
        details['poster'] = ''

    # Plot/popis
    plot_match = re.search(r'itemprop="description"[^>]*>(.*?)</div>', html, re.DOTALL)
    if not plot_match:
        plot_match = re.search(r'class="[^"]*plot[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if plot_match:
        details['plot'] = re.sub(r'<[^>]+>', '', plot_match.group(1)).strip()
    else:
        details['plot'] = ''

    # Žánry
    genres = re.findall(r'itemprop="genre"[^>]*>(.*?)</span>', html)
    if not genres:
        genres = re.findall(r'/podrobnosti/\?genre=\d+"[^>]*>([^<]+)</a>', html)
    details['genres'] = [re.sub(r'<[^>]+>', '', g).strip() for g in genres]

    # Režiséři
    directors = re.findall(r'itemprop="director"[^>]*>.*?itemprop="name"[^>]*>(.*?)</span>', html, re.DOTALL)
    if not directors:
        directors_block = re.search(r'Režie:.*?</div>', html, re.DOTALL)
        if directors_block:
            directors = re.findall(r'<a[^>]*/tvurce/[^>]+>([^<]+)</a>', directors_block.group(0))
    details['directors'] = [re.sub(r'<[^>]+>', '', d).strip() for d in directors]

    # Herci
    actors_raw = re.findall(r'itemprop="actor"[^>]*>.*?itemprop="name"[^>]*>(.*?)</span>', html, re.DOTALL)
    if not actors_raw:
        actors_block = re.search(r'Hrají:.*?</div>', html, re.DOTALL)
        if actors_block:
            actors_raw = re.findall(r'<a[^>]*/tvurce/[^>]+>([^<]+)</a>', actors_block.group(0))
    details['actors'] = [re.sub(r'<[^>]+>', '', a).strip() for a in actors_raw[:10]]

    return details


def get_popular(media_type='movie', genre=None, limit=30):
    """
    Vrátí populární filmy/seriály z CSFD žebříčků.
    media_type: 'movie' nebo 'tvshow'
    genre: volitelný žánr
    """
    if media_type == 'movie':
        url = '%s/zebricky/nejlepsi-filmy/?show=all' % CSFD_BASE
    else:
        url = '%s/zebricky/nejlepsi-serialy/?show=all' % CSFD_BASE

    html = _fetch(url)
    if not html:
        return []

    results = []
    seen_ids = set()

    # Žebříček - každá položka má pořadí, název, rok, hodnocení
    # Pattern pro řádky žebříčku
    row_pattern = r'<tr[^>]*>(.*?)</tr>'
    rows = re.findall(row_pattern, html, re.DOTALL)

    for row in rows:
        if '/film/' not in row:
            continue

        film_match = re.search(r'href="(/film/(\d+)[^"]*)"[^>]*>([^<]+)</a>', row)
        if not film_match:
            continue

        film_id = film_match.group(2)
        if film_id in seen_ids:
            continue
        seen_ids.add(film_id)

        title = film_match.group(3).strip()
        year_match = re.search(r'\((\d{4})\)', row)
        year = year_match.group(1) if year_match else ''
        rating_match = re.search(r'(\d+)\s*%', row)
        rating = rating_match.group(1) + '%' if rating_match else ''

        results.append({
            'id': film_id,
            'title': title,
            'year': year,
            'rating': rating,
            'poster': '',
            'type': media_type,
            'url': CSFD_BASE + film_match.group(1)
        })

        if len(results) >= limit:
            break

    return results


def get_genres():
    """Vrátí dostupné žánry z CSFD."""
    return [
        ('Akční', 'akcni'),
        ('Animovaný', 'animovany'),
        ('Dokumentární', 'dokumentarni'),
        ('Drama', 'drama'),
        ('Fantasy', 'fantasy'),
        ('Horor', 'horor'),
        ('Komedie', 'komedie'),
        ('Krimi', 'krimi'),
        ('Muzikál', 'muzikal'),
        ('Rodinný', 'rodinny'),
        ('Romance', 'romance'),
        ('Sci-Fi', 'sci-fi'),
        ('Thriller', 'thriller'),
        ('Western', 'western'),
    ]
