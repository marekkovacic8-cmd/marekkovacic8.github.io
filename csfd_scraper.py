# -*- coding: utf-8 -*-
"""
OMDB API modul — Stream Cinema Caolina
Doplňkový zdroj metadat (plot EN, imdb_id, awards...)
Plakáty se NEVYUŽÍVAJÍ z OMDB — vždy preferujeme TMDB.
API key: 3e593e30
"""

import json
import re
import xbmc

try:
    from urllib.request import urlopen, Request
    from urllib.parse import urlencode, quote
except ImportError:
    from urllib2 import urlopen, Request
    from urllib import urlencode, quote

OMDB_API = 'https://www.omdbapi.com/'
OMDB_KEY = '3e593e30'


def _get(params):
    params['apikey'] = OMDB_KEY
    try:
        url = OMDB_API + '?' + urlencode(params)
        req = Request(url, headers={'User-Agent': 'StreamCinema/1.0'})
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('Response') == 'True':
            return data
    except Exception as e:
        xbmc.log('OMDB API error: %s' % str(e), xbmc.LOGERROR)
    return {}


def search_movie(title, year=''):
    """Vyhledá film, vrátí list výsledků [{imdb_id, title, year, type}]."""
    params = {'s': title, 'type': 'movie'}
    if year:
        params['y'] = str(year)
    data = _get(params)
    results = []
    for item in data.get('Search', []):
        results.append({
            'imdb_id': item.get('imdbID', ''),
            'title':   item.get('Title', ''),
            'year':    item.get('Year', ''),
            'type':    item.get('Type', 'movie'),
            'source':  'omdb',
        })
    return results


def get_movie_details(imdb_id='', title='', year=''):
    """
    Vrátí detaily pro film/seriál.
    Preferuj imdb_id, fallback na title+year.
    Plakát záměrně VYNECHÁME — použijeme TMDB.
    """
    if imdb_id:
        data = _get({'i': imdb_id, 'plot': 'full'})
    elif title:
        params = {'t': title, 'plot': 'full'}
        if year:
            params['y'] = str(year)
        data = _get(params)
    else:
        return {}

    if not data:
        return {}

    # Parsuj hodnocení — vrátí jen IMDb (bez CSFD/TMDB aby nedošlo k duplikaci)
    imdb_rating = ''
    try:
        r = data.get('imdbRating', '')
        if r and r != 'N/A':
            imdb_rating = 'IMDb %.1f' % float(r)
    except (ValueError, TypeError):
        pass

    # Herci — string oddělený čárkami → list
    actors_str = data.get('Actors', '')
    actors = [a.strip() for a in actors_str.split(',') if a.strip() and a.strip() != 'N/A']

    directors_str = data.get('Director', '')
    directors = [d.strip() for d in directors_str.split(',') if d.strip() and d.strip() != 'N/A']

    genres_str = data.get('Genre', '')
    genres = [g.strip() for g in genres_str.split(',') if g.strip() and g.strip() != 'N/A']

    runtime = data.get('Runtime', '')
    if runtime and runtime != 'N/A':
        m = re.search(r'(\d+)', runtime)
        runtime_min = int(m.group(1)) if m else 0
    else:
        runtime_min = 0

    plot = data.get('Plot', '')
    if plot == 'N/A':
        plot = ''

    return {
        'imdb_id':    data.get('imdbID', ''),
        'title':      data.get('Title', ''),
        'year':       data.get('Year', ''),
        'plot_en':    plot,                    # Anglický plot
        'genres':     genres,
        'directors':  directors,
        'actors':     actors,
        'runtime':    runtime_min,
        'imdb_rating': imdb_rating,            # Formátovaný string pro zobrazení
        'imdb_votes': data.get('imdbVotes', ''),
        'country':    data.get('Country', ''),
        'language':   data.get('Language', ''),
        'awards':     data.get('Awards', ''),
        'rated':      data.get('Rated', ''),
        'source':     'omdb',
        # Plakát z OMDB NEVRACÍME — poster se bere vždy z TMDB
    }
