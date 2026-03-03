# -*- coding: utf-8 -*-
"""
TMDB API modul — Stream Cinema Caolina
Plakáty a backdrop vždy z TMDB (nejlepší kvalita).
Hodnocení: NEVRACÍME (požadavek uživatele — bez ratingu v labelu).
"""

import json
import xbmc

try:
    from urllib.request import urlopen, Request
    from urllib.parse import urlencode, quote
except ImportError:
    from urllib2 import urlopen, Request
    from urllib import urlencode, quote

TMDB_BASE    = 'https://api.themoviedb.org/3'
TMDB_IMG     = 'https://image.tmdb.org/t/p/'
POSTER_SIZE  = 'w500'
BACKDROP_SIZE = 'w1280'

MOVIE_GENRES = {
    28: 'Akční', 12: 'Dobrodružný', 16: 'Animovaný', 35: 'Komedie',
    80: 'Krimi', 99: 'Dokumentární', 18: 'Drama', 10751: 'Rodinný',
    14: 'Fantasy', 36: 'Historický', 27: 'Horor', 10402: 'Hudební',
    9648: 'Mysteriózní', 10749: 'Romantický', 878: 'Sci-Fi',
    10770: 'TV film', 53: 'Thriller', 10752: 'Válečný', 37: 'Western',
}

TV_GENRES = {
    10759: 'Akční & dobrodružný', 16: 'Animovaný', 35: 'Komedie',
    80: 'Krimi', 99: 'Dokumentární', 18: 'Drama', 10751: 'Rodinný',
    10762: 'Pro děti', 9648: 'Mysteriózní', 10763: 'Zprávy',
    10764: 'Reality', 10765: 'Sci-Fi & Fantasy', 10766: 'Soap opera',
    10767: 'Talk show', 10768: 'Válka & politika', 37: 'Western',
}


def _get(path, params, api_key):
    params['api_key'] = api_key
    params.setdefault('language', 'cs')
    params.setdefault('region', 'CZ')
    url = TMDB_BASE + path + '?' + urlencode(params)
    try:
        req = Request(url, headers={'User-Agent': 'StreamCinema/1.0'})
        resp = urlopen(req, timeout=10)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        xbmc.log('TMDB API [%s] error: %s' % (path, str(e)), xbmc.LOGERROR)
        return {}


def poster_url(path, size=POSTER_SIZE):
    if not path:
        return ''
    return TMDB_IMG + size + path


def backdrop_url(path, size=BACKDROP_SIZE):
    if not path:
        return ''
    return TMDB_IMG + size + path


def _parse_movie(item):
    """Převede TMDB movie item na standardizovaný dict. BEZ ratingu."""
    year = ''
    rd = item.get('release_date', '')
    if rd and len(rd) >= 4:
        year = rd[:4]
    genres = item.get('genre_ids', [])
    genre_names = [MOVIE_GENRES.get(g, '') for g in genres if g in MOVIE_GENRES]
    return {
        'id':        str(item.get('id', '')),
        'tmdb_id':   str(item.get('id', '')),
        'title':     item.get('title', '') or item.get('original_title', ''),
        'orig_title': item.get('original_title', ''),
        'year':      year,
        'plot':      item.get('overview', ''),
        'poster':    poster_url(item.get('poster_path', '')),
        'backdrop':  backdrop_url(item.get('backdrop_path', '')),
        'genres':    [g for g in genre_names if g],
        'type':      'movie',
        'source':    'tmdb',
        # rating záměrně vynecháno
    }


def _parse_tv(item):
    """Převede TMDB TV item na standardizovaný dict. BEZ ratingu."""
    year = ''
    fa = item.get('first_air_date', '')
    if fa and len(fa) >= 4:
        year = fa[:4]
    genres = item.get('genre_ids', [])
    genre_names = [TV_GENRES.get(g, '') for g in genres if g in TV_GENRES]

    # title = lokalizovaný (CZ) pro zobrazení uživateli
    # orig_title = VŽDY anglický originál — používá se pro WS search!
    cz_name   = item.get('name', '')
    orig_name = item.get('original_name', '')
    display   = cz_name or orig_name   # zobrazení: preferuj CZ

    return {
        'id':        str(item.get('id', '')),
        'tmdb_id':   str(item.get('id', '')),
        'title':     display,       # CZ název (nebo EN pokud CZ nemá)
        'orig_title': orig_name,    # EN originál — VŽDY pro WS search
        'year':      year,
        'plot':      item.get('overview', ''),
        'poster':    poster_url(item.get('poster_path', '')),
        'backdrop':  backdrop_url(item.get('backdrop_path', '')),
        'genres':    [g for g in genre_names if g],
        'type':      'tvshow',
        'source':    'tmdb',
    }


def search_movies(api_key, query, year=''):
    params = {'query': query}
    if year:
        params['year'] = str(year)
    data = _get('/search/movie', params, api_key)
    return [_parse_movie(r) for r in data.get('results', [])]


def search_tvshows(api_key, query):
    data = _get('/search/tv', {'query': query}, api_key)
    return [_parse_tv(r) for r in data.get('results', [])]


def get_movie_details(api_key, tmdb_id):
    data = _get('/movie/%s' % tmdb_id, {'append_to_response': 'credits'}, api_key)
    if not data:
        return {}
    year = ''
    rd = data.get('release_date', '')
    if rd and len(rd) >= 4:
        year = rd[:4]
    genres = [g.get('name', '') for g in data.get('genres', [])]
    credits = data.get('credits', {})
    directors = [c['name'] for c in credits.get('crew', []) if c.get('job') == 'Director']
    actors    = [c['name'] for c in credits.get('cast', [])[:10]]
    return {
        'id':         str(data.get('id', '')),
        'tmdb_id':    str(data.get('id', '')),
        'imdb_id':    data.get('imdb_id', ''),
        'title':      data.get('title', ''),
        'orig_title': data.get('original_title', ''),
        'year':       year,
        'plot':       data.get('overview', ''),
        'poster':     poster_url(data.get('poster_path', '')),
        'backdrop':   backdrop_url(data.get('backdrop_path', '')),
        'genres':     genres,
        'directors':  directors,
        'actors':     actors,
        'runtime':    data.get('runtime', 0),
        'type':       'movie',
        'source':     'tmdb',
    }


def get_tvshow_details(api_key, tmdb_id):
    data = _get('/tv/%s' % tmdb_id, {'append_to_response': 'credits'}, api_key)
    if not data:
        return {}
    year = ''
    fa = data.get('first_air_date', '')
    if fa and len(fa) >= 4:
        year = fa[:4]
    genres = [g.get('name', '') for g in data.get('genres', [])]
    credits = data.get('credits', {})
    creators  = [c.get('name', '') for c in data.get('created_by', [])]
    actors    = [c['name'] for c in credits.get('cast', [])[:10]]
    return {
        'id':         str(data.get('id', '')),
        'tmdb_id':    str(data.get('id', '')),
        'title':      data.get('name', ''),
        'orig_title': data.get('original_name', ''),
        'year':       year,
        'plot':       data.get('overview', ''),
        'poster':     poster_url(data.get('poster_path', '')),
        'backdrop':   backdrop_url(data.get('backdrop_path', '')),
        'genres':     genres,
        'creators':   creators,
        'actors':     actors,
        'seasons':    data.get('number_of_seasons', 0),
        'episodes':   data.get('number_of_episodes', 0),
        'type':       'tvshow',
        'source':     'tmdb',
    }


def get_popular_movies(api_key, page=1):
    data = _get('/movie/popular', {'page': page}, api_key)
    return [_parse_movie(r) for r in data.get('results', [])]


def get_popular_tvshows(api_key, page=1):
    data = _get('/tv/popular', {'page': page}, api_key)
    return [_parse_tv(r) for r in data.get('results', [])]


def get_trending(api_key, media_type='movie', time_window='week'):
    data = _get('/trending/%s/%s' % (media_type, time_window), {}, api_key)
    results = []
    for r in data.get('results', []):
        if r.get('media_type') == 'tv' or media_type == 'tv':
            results.append(_parse_tv(r))
        else:
            results.append(_parse_movie(r))
    return results


def discover_movies(api_key, genre_id='', year='', sort_by='popularity.desc', page=1, country_code=''):
    params = {'sort_by': sort_by, 'page': page}
    if genre_id:
        params['with_genres'] = str(genre_id)
    if year:
        params['primary_release_year'] = str(year)
    if country_code:
        params['with_origin_country'] = country_code
    data = _get('/discover/movie', params, api_key)
    results = [_parse_movie(r) for r in data.get('results', [])]
    return results, data.get('total_pages', 1)


def discover_tvshows(api_key, genre_id='', sort_by='popularity.desc', page=1, country_code=''):
    params = {'sort_by': sort_by, 'page': page}
    if genre_id:
        params['with_genres'] = str(genre_id)
    if country_code:
        params['with_origin_country'] = country_code
    data = _get('/discover/tv', params, api_key)
    results = [_parse_tv(r) for r in data.get('results', [])]
    return results, data.get('total_pages', 1)


def get_tv_season(api_key, tmdb_id, season_number):
    """Vraci detaily sezony vcetne epizod (name, overview, episode_number)."""
    data = _get('/tv/%s/season/%s' % (tmdb_id, season_number), {}, api_key)
    return data or {}


def get_genres(api_key, media_type='movie'):
    if media_type == 'movie':
        return list(MOVIE_GENRES.items())
    return list(TV_GENRES.items())
