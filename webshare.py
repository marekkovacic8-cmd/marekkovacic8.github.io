# -*- coding: utf-8 -*-
"""
Stream Cinema Caolina v2.1.0 — Kodi plugin
Menu identické s Enigma2 provider.py (CaolinaVideoContentProvider)
"""

import sys, os, re, json, time as _time_mod

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

try:
    import xbmcvfs
    _translate_path = xbmcvfs.translatePath
except (ImportError, AttributeError):
    _translate_path = xbmc.translatePath

try:
    from urllib.parse import parse_qsl, urlencode
except ImportError:
    from urlparse import parse_qsl
    from urllib import urlencode

import tmdb_api
import webshare

# ══════════════════════════════════════════════════════════════════════════════
#  INICIALIZACE
# ══════════════════════════════════════════════════════════════════════════════

addon        = xbmcaddon.Addon()
addon_handle = int(sys.argv[1])
addon_url    = sys.argv[0]

profile_path = _translate_path(addon.getAddonInfo('profile'))
if not os.path.exists(profile_path):
    try: os.makedirs(profile_path)
    except: pass

WATCHED_FILE = os.path.join(profile_path, 'watched.json')
TOKEN_FILE   = os.path.join(profile_path, 'ws_token.json')
TMDB_KEY     = addon.getSetting('tmdb_api_key') or 'a9d851cb36fd8287fed226766d7f01ab'

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS — identické s provider.py
# ══════════════════════════════════════════════════════════════════════════════

COUNTRY_NAMES = {
    'US':'USA','GB':'Velka Britanie','CZ':'Ceska republika','SK':'Slovensko',
    'DE':'Nemecko','FR':'Francie','IT':'Italie','ES':'Spanelsko','PL':'Polsko',
    'RU':'Rusko','AU':'Australie','CA':'Kanada','JP':'Japonsko','KR':'Jizni Korea',
    'CN':'Cina','IN':'Indie','SE':'Svedsko','NO':'Norsko','DK':'Dansko',
    'FI':'Finsko','NL':'Nizozemsko','BE':'Belgie','AT':'Rakousko','CH':'Svycarsko',
    'HU':'Madarsko','BR':'Brazilie','MX':'Mexiko','AR':'Argentina','ZA':'Jizni Afrika',
    'IE':'Irsko','PT':'Portugalsko','TR':'Turecko','IL':'Izrael','TH':'Thajsko',
}
FEATURED_COUNTRIES_MOVIE  = ['US','GB','CZ','SK','DE','FR','IT','ES','AU','CA','JP','KR','RU','PL','SE','DK','NO']
FEATURED_COUNTRIES_TVSHOW = ['US','GB','CZ','SK','DE','FR','KR','JP','SE','DK','NO','AU','CA','RU','PL']

QUALITY_PATTERN = (
    r'\b(720p|1080p|2160p|4K|UHD|BluRay|BRRip|WEBRip|HDTV|WEB-DL|DVDRip|'
    r'x264|x265|HEVC|H\.264|H\.265|AAC|AC3|DTS|'
    r'CZ|SK|EN|MULTI|DUAL|SUB|DUBBED|'
    r'KINORIP|CAMRIP|TELESYNC|TS|CAM|SCREENER|'
    r'REMUX|PROPER|REPACK|UNRATED|EXTENDED|'
    r'DD5\.1|TrueHD|ATMOS)\b'
)

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _norm(s):
    """Normalizuje string pro porovnání — odstraní diakritiku, lowercase."""
    import unicodedata
    try:
        if isinstance(s, bytes): s = s.decode('utf-8')
        n = unicodedata.normalize('NFD', s)
        return u''.join(c for c in n if unicodedata.category(c) != 'Mn').lower().strip()
    except:
        return (s or '').lower().strip()


def _url(**kw):
    safe = {}
    for k, v in kw.items():
        if v is None: v = ''
        if isinstance(v, (list, dict)): v = json.dumps(v, ensure_ascii=False)
        safe[str(k)] = str(v)
    return addon_url + '?' + urlencode(safe)


def _set_info(li, info, is_folder=False):
    """Nastavi video info na ListItem."""
    try:
        tag = li.getVideoInfoTag()
        if info.get('title'):    tag.setTitle(info['title'])
        if info.get('plot'):     tag.setPlot(info['plot'])
        if info.get('year'):
            try: tag.setYear(int(info['year']))
            except: pass
        if info.get('genre'):    tag.setGenres([info['genre']])
        if info.get('director'): tag.setDirectors([info['director']])
        if info.get('duration'):
            try: tag.setDuration(int(info['duration']))
            except: pass
        if info.get('season'):
            try: tag.setSeason(int(info['season']))
            except: pass
        if info.get('episode'):
            try: tag.setEpisode(int(info['episode']))
            except: pass
        if info.get('cast'):
            try: tag.setCast([xbmc.Actor(n,'',0,'') for n in info['cast'][:10]])
            except: pass
        tag.setMediaType(info.get('mediatype','movie'))
    except AttributeError:
        # Kodi 17 fallback
        kodi_info = {k: v for k, v in info.items()
                     if k in ('title','plot','year','genre','director','duration',
                               'cast','season','episode','mediatype')}
        li.setInfo('video', kodi_info)


def _notify(msg, icon=xbmcgui.NOTIFICATION_INFO, ms=3000):
    xbmcgui.Dialog().notification('Stream Cinema Caolina', msg, icon, ms)


def _add_dir(label, url, folder=True, img='', info=None, is_playable=False):
    li = xbmcgui.ListItem(label)
    if img:
        li.setArt({'thumb': img, 'poster': img, 'icon': img, 'fanart': img})
    if info:
        _set_info(li, info, is_folder=folder)
    if is_playable:
        li.setProperty('IsPlayable', 'true')
    xbmcplugin.addDirectoryItem(addon_handle, url, li, folder)


def _end(update_listing=False):
    xbmcplugin.endOfDirectory(addon_handle, updateListing=update_listing)


def _fail(msg=''):
    if msg:
        _notify(msg, xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(addon_handle, succeeded=False)


# ══════════════════════════════════════════════════════════════════════════════
#  TOKEN / LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def _load_token():
    try:
        if os.path.exists(TOKEN_FILE):
            return json.load(open(TOKEN_FILE, 'r')).get('token')
    except: pass
    return None


def _save_token(token):
    try:
        json.dump({'token': token}, open(TOKEN_FILE, 'w'))
    except: pass


def _get_token(force=False):
    if not force:
        t = _load_token()
        if t: return t
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        xbmcgui.Dialog().ok('Stream Cinema Caolina',
                            'Zadejte Webshare.cz prihlasovaci udaje v Nastaveni.')
        addon.openSettings()
        username = addon.getSetting('username')
        password = addon.getSetting('password')
    if not username or not password:
        return None
    token = webshare.login(username, password)
    if token:
        _save_token(token)
    else:
        xbmcgui.Dialog().ok('Stream Cinema Caolina',
                            'Prihlaseni k Webshare.cz selhalo.\nZkontrolujte jmeno a heslo.')
    return token


# ══════════════════════════════════════════════════════════════════════════════
#  WATCHED
# ══════════════════════════════════════════════════════════════════════════════

def _load_watched():
    try:
        if os.path.exists(WATCHED_FILE):
            return json.load(open(WATCHED_FILE, 'r'))
    except: pass
    return {}


def _save_watched(data):
    try:
        json.dump(data, open(WATCHED_FILE, 'w'), indent=2)
    except: pass


def _trim_watched(watched):
    max_w = int(addon.getSetting('max_watched') or '50')
    if len(watched) > max_w:
        for k, _ in sorted(watched.items(), key=lambda i: i[1]['time'], reverse=True)[max_w:]:
            del watched[k]
    return watched


# ══════════════════════════════════════════════════════════════════════════════
#  ROOT MENU — identicky s provider.py root()
# ══════════════════════════════════════════════════════════════════════════════

def main_menu():
    xbmcplugin.setContent(addon_handle, 'videos')
    use_tmdb = addon.getSetting('use_tmdb') != 'false'

    # Stav uctu — identicky s show_account_status()
    _show_account_status()

    # Vyhledavani — identicky s add_search_dir()
    _add_dir('[B]Hledat[/B]', _url(mode='search'), img='DefaultAddonsSearch.png')

    # Filmy
    _add_dir('[B]Filmy[/B]', _url(mode='media_root', media_type='movie'),
             img='DefaultMovies.png')

    # Serialy
    _add_dir('[B]Serialy[/B]', _url(mode='media_root', media_type='tvshow'),
             img='DefaultTVShows.png')

    # Trendy + Popularni — jen pokud TMDB
    if use_tmdb:
        _add_dir('[B]Trendy filmy[/B]', _url(mode='trending_movies'),
                 img='DefaultRecentlyAddedMovies.png')
        _add_dir('[B]Popularni filmy[/B]', _url(mode='popular_movies'),
                 img='DefaultRecentlyAddedMovies.png')

    # Dobrovolny prispevek
    _add_dir('[COLOR gold]♥ Dobrovolny prispevek na vyvoj[/COLOR]',
             _url(mode='donation'), img='DefaultAddonService.png')

    _end()


def _show_account_status():
    """Zobrazí stav účtu v hlavním menu — s VIP dobou platnosti."""
    token = _load_token()
    if token:
        try:
            xml = webshare._post('user_data', {}, token=token)
            if xml and webshare._x(xml, 'status') == 'OK':
                username = webshare._x(xml, 'username') or addon.getSetting('username') or '?'
                vip      = webshare._x(xml, 'vip') == '1'
                vip_days = webshare._x(xml, 'vip_days')

                if vip and vip_days and str(vip_days).isdigit():
                    # "Uzivatel [VIP | 247 dní]"
                    badge = ' [COLOR lime][VIP | %s dní][/COLOR]' % vip_days
                elif vip:
                    badge = ' [COLOR lime][VIP][/COLOR]'
                else:
                    badge = ' [COLOR gray][Free][/COLOR]'

                _add_dir('[B]Ucet: %s%s[/B]' % (username, badge),
                         _url(mode='account_info'), img='DefaultAddonService.png')
                return
        except: pass
    _add_dir('Prihlasit se na Webshare.cz', _url(mode='do_login'),
             img='DefaultAddonService.png')


# ══════════════════════════════════════════════════════════════════════════════
#  UCET
# ══════════════════════════════════════════════════════════════════════════════

def show_account_info():
    """Identicky s provider.py show_account_info()."""
    token = _load_token()
    if not token:
        xbmcgui.Dialog().ok('Stream Cinema Caolina', 'Nejste prihlaseni.')
        return _fail()
    try:
        xml = webshare._post('user_data', {}, token=token)
        if xml and webshare._x(xml, 'status') == 'OK':
            username = webshare._x(xml, 'username')
            email    = webshare._x(xml, 'email')
            vip      = webshare._x(xml, 'vip') == '1'
            vip_days = webshare._x(xml, 'vip_days')
            vip_text = ('ANO (%s dni)' % vip_days) if (vip and vip_days) else ('ANO' if vip else 'NE (viz webshare.cz)')
            xbmcgui.Dialog().ok('Webshare ucet',
                'Uzivatel: %s\nE-mail: %s\nVIP: %s' % (username, email, vip_text))
    except Exception as e:
        xbmcgui.Dialog().ok('Stream Cinema Caolina', 'Nelze nacist data uctu:\n%s' % str(e))
    _fail()


def do_login():
    """Identicky s provider.py do_manual_login()."""
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password:
        xbmcgui.Dialog().ok('Stream Cinema Caolina', 'Zadejte udaje v Nastaveni doplnku.')
        addon.openSettings()
        return _fail()
    token = webshare.login(username, password)
    if token:
        _save_token(token)
        try:
            xml  = webshare._post('user_data', {}, token=token)
            uname = webshare._x(xml, 'username') if xml else username
            vip   = webshare._x(xml, 'vip') == '1' if xml else False
            badge = ' (VIP)' if vip else ' (Free)'
            xbmcgui.Dialog().ok('Stream Cinema Caolina', 'Prihlasen: %s%s' % (uname, badge))
        except:
            _notify('Prihlaseni uspesne!')
    else:
        xbmcgui.Dialog().ok('Stream Cinema Caolina',
                            'Prihlaseni selhalo.\nZkontrolujte jmeno a heslo.')
    _fail()


# ══════════════════════════════════════════════════════════════════════════════
#  MEDIA ROOT — podmenu Filmů / Seriálů
#  Identicky s provider.py root(media_type='movie'/'tvshow')
# ══════════════════════════════════════════════════════════════════════════════

def media_root(media_type):
    xbmcplugin.setContent(addon_handle, 'videos')
    use_tmdb = addon.getSetting('use_tmdb') != 'false'

    # Naposledy sledovane — identicky s show_last_seen_dir()
    watched = _load_watched()
    if any(v.get('media_type') == media_type for v in watched.values()):
        _add_dir('Naposledy sledovane',
                 _url(mode='watched_list', media_type=media_type),
                 img='DefaultRecentlyAddedMovies.png')

    # Vyhledavani — identicky s add_search_dir(search_id=media_type)
    _add_dir('[B]Hledat[/B]', _url(mode='search', search_id=media_type),
             img='DefaultAddonsSearch.png')

    # Podle abecedy
    _add_dir('Podle abecedy', _url(mode='alphabet_root', media_type=media_type),
             img='DefaultMusicAlbums.png')

    if use_tmdb:
        # Podle zanru
        _add_dir('Podle zanru', _url(mode='genre_list', media_type=media_type),
                 img='DefaultGenre.png')
        # Podle statu
        _add_dir('Podle statu', _url(mode='country_list', media_type=media_type),
                 img='DefaultCountry.png')

    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  ZANRY — identicky s provider.py show_genre_list() / show_genre_movies()
# ══════════════════════════════════════════════════════════════════════════════

def show_genre_list(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    genres = tmdb_api.get_genres(TMDB_KEY, media_type=media_type)
    # get_genres vraci [(id, name), ...] — seradime abecedne podle name
    for gid, gname in sorted(genres, key=lambda g: g[1]):
        _add_dir('[B]%s[/B]' % gname,
                 _url(mode='genre_movies', genre_id=gid, genre_name=gname,
                      media_type=media_type))
    _end()


def show_genre_movies(genre_id, genre_name, media_type='movie', page=1):
    xbmcplugin.setContent(addon_handle, 'movies' if media_type == 'movie' else 'tvshows')
    page = int(page)
    try:
        if media_type == 'movie':
            results, total_pages = tmdb_api.discover_movies(
                TMDB_KEY, genre_id=genre_id, page=page)
        else:
            results, total_pages = tmdb_api.discover_tvshows(
                TMDB_KEY, genre_id=genre_id, page=page)
    except Exception as e:
        xbmc.log('SCC genre_movies: %s' % e, xbmc.LOGERROR)
        results, total_pages = [], 1

    for item in results:
        _add_tmdb_item(item, media_type)

    if page < total_pages:
        _add_dir('[B]>> Dalsi strana (%d/%d)[/B]' % (page + 1, total_pages),
                 _url(mode='genre_movies', genre_id=genre_id, genre_name=genre_name,
                      media_type=media_type, page=page + 1))
    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  STATY — identicky s provider.py show_country_list() / show_country_movies()
# ══════════════════════════════════════════════════════════════════════════════

def show_country_list(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    countries = FEATURED_COUNTRIES_MOVIE if media_type == 'movie' else FEATURED_COUNTRIES_TVSHOW
    for code in sorted(countries, key=lambda c: COUNTRY_NAMES.get(c, c)):
        name = COUNTRY_NAMES.get(code, code)
        _add_dir('[B]%s[/B]' % name,
                 _url(mode='country_movies', country_code=code,
                      country_name=name, media_type=media_type))
    _end()


def show_country_movies(country_code, country_name, media_type='movie', page=1):
    xbmcplugin.setContent(addon_handle, 'movies' if media_type == 'movie' else 'tvshows')
    page = int(page)
    try:
        if media_type == 'movie':
            results, total_pages = tmdb_api.discover_movies(
                TMDB_KEY, page=page, country_code=country_code)
        else:
            results, total_pages = tmdb_api.discover_tvshows(
                TMDB_KEY, page=page, country_code=country_code)
    except Exception as e:
        xbmc.log('SCC country_movies: %s' % e, xbmc.LOGERROR)
        results, total_pages = [], 1

    for item in results:
        _add_tmdb_item(item, media_type)

    if page < total_pages:
        _add_dir('[B]>> Dalsi strana (%d/%d)[/B]' % (page + 1, total_pages),
                 _url(mode='country_movies', country_code=country_code,
                      country_name=country_name, media_type=media_type, page=page + 1))
    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  TRENDING / POPULAR — identicky s provider.py
# ══════════════════════════════════════════════════════════════════════════════

def show_trending_movies(page=1):
    xbmcplugin.setContent(addon_handle, 'movies')
    try:
        results = tmdb_api.get_trending(TMDB_KEY, media_type='movie')
    except: results = []
    for item in results:
        _add_tmdb_item(item, 'movie')
    _end()


def show_popular_movies(page=1):
    xbmcplugin.setContent(addon_handle, 'movies')
    page = int(page)
    try:
        result = tmdb_api.get_popular_movies(TMDB_KEY, page=page)
        results, total = (result if isinstance(result, tuple) else (result, 1))
    except: results, total = [], 1
    for item in results:
        _add_tmdb_item(item, 'movie')
    if page < total:
        _add_dir('[B]>> Dalsi strana[/B]', _url(mode='popular_movies', page=page + 1))
    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  ZOBRAZENI TMDB POLOZKY — identicky s _show_tmdb_movie_item / _show_tmdb_tvshow_item
# ══════════════════════════════════════════════════════════════════════════════

def _add_tmdb_item(item, media_type):
    """
    Prida film nebo serial do listingu.
    Odpovida provider.py _show_tmdb_movie_item / _show_tmdb_tvshow_item.
    """
    title    = item.get('title', '')
    year     = item.get('year', '')
    plot     = item.get('plot', '')
    poster   = item.get('poster', '')
    backdrop = item.get('backdrop', '')
    tmdb_id  = item.get('tmdb_id', item.get('id', ''))
    orig     = item.get('orig_title', title)
    genres   = item.get('genres', [])

    year_str = ' (%s)' % year if year else ''
    label    = '%s%s' % (title, year_str)

    li = xbmcgui.ListItem(label)
    li.setArt({'thumb': poster, 'poster': poster,
               'fanart': backdrop or poster, 'icon': poster})
    info = {
        'title':     title,
        'plot':      plot,
        'year':      int(year) if year and str(year).isdigit() else 0,
        'genre':     ', '.join(genres) if genres else '',
        'mediatype': 'movie' if media_type == 'movie' else 'tvshow',
    }
    _set_info(li, info)

    if media_type == 'movie':
        url = _url(mode='select_quality', title=title, year=year,
                   orig_title=orig, tmdb_id=tmdb_id)
    else:
        url = _url(mode='series_list', serial_title=title, serial_year=year,
                   serial_original_name=orig, tmdb_id=tmdb_id)

    xbmcplugin.addDirectoryItem(addon_handle, url, li, True)


# ══════════════════════════════════════════════════════════════════════════════
#  VYHLEDAVANI — identicky s provider.py search()
# ══════════════════════════════════════════════════════════════════════════════

def do_search(search_id=''):
    kb = xbmc.Keyboard('', 'Hledat ' + ('serial' if search_id == 'tvshow' else 'film'))
    kb.doModal()
    if not kb.isConfirmed() or not kb.getText().strip():
        return _fail()
    keyword  = kb.getText().strip()
    use_tmdb = addon.getSetting('use_tmdb') != 'false'

    # Identicky s provider.py search()
    if search_id == 'tvshow':
        if use_tmdb:
            _search_series_with_tmdb(keyword)
        else:
            show_series_list(serial_title=keyword)
    elif use_tmdb:
        _search_movies_with_tmdb(keyword, page=1)
    else:
        _do_search_files(keyword, media_type=search_id or 'movie')


def _search_movies_with_tmdb(keyword, page=1):
    """Identicky s provider.py _search_movies_with_tmdb()."""
    xbmcplugin.setContent(addon_handle, 'movies')
    page = int(page)
    try:
        raw = tmdb_api.search_movies(TMDB_KEY, keyword, page=page)
        results, total_pages = (raw if isinstance(raw, tuple) else (raw, 1))
    except Exception as e:
        xbmc.log('SCC search_movies: %s' % e, xbmc.LOGERROR)
        results, total_pages = [], 1

    if not results:
        # Fallback na WS primo — identicky s provider.py
        _do_search_files(keyword, media_type='movie')
        return

    for item in results:
        _add_tmdb_item(item, 'movie')

    if page < total_pages:
        _add_dir('[B]>> Dalsi strana[/B]',
                 _url(mode='search_more', keyword=keyword, search_id='movie', page=page + 1))
    _end()


def _search_series_with_tmdb(keyword):
    """Identicky s provider.py _search_series_with_tmdb()."""
    xbmcplugin.setContent(addon_handle, 'tvshows')
    try:
        raw = tmdb_api.search_tvshows(TMDB_KEY, keyword)
        results = (raw[0] if isinstance(raw, tuple) else raw)
    except Exception as e:
        xbmc.log('SCC search_tvshows: %s' % e, xbmc.LOGERROR)
        results = []

    if not results:
        # Fallback — identicky s provider.py
        show_series_list(serial_title=keyword)
        return

    for item in results:
        _add_tmdb_item(item, 'tvshow')
    _end()


def search_more(keyword, search_id='movie', page=1):
    page = int(page)
    if search_id == 'tvshow':
        _search_series_with_tmdb(keyword)
    else:
        _search_movies_with_tmdb(keyword, page=page)


# ══════════════════════════════════════════════════════════════════════════════
#  WEBSHARE SOUBORY — identicky s _do_search_files / _show_file_items / _add_video_item
# ══════════════════════════════════════════════════════════════════════════════

def _do_search_files(query, media_type='movie'):
    """Identicky s provider.py _do_search_files()."""
    token = _get_token()
    if not token: return _fail()

    prog = xbmcgui.DialogProgress()
    prog.create('Stream Cinema Caolina', 'Hledani: %s' % query)
    try:
        files = webshare.search_for_title(token, query)
    except:
        files = []
    finally:
        prog.close()

    if not files:
        return _fail('Zadne vysledky pro: %s' % query)

    xbmcplugin.setContent(addon_handle, 'movies' if media_type == 'movie' else 'tvshows')
    _show_file_items(files, media_type=media_type)
    _end()


def _show_file_items(files, media_type='movie', poster='', backdrop=''):
    """
    Identicky s provider.py _show_file_items().
    Grupuje soubory podle nazvu (bez quality tagů).
    """
    grouped = {}
    for f in files:
        base = re.sub(QUALITY_PATTERN, '', f['name'], flags=re.I)
        base = re.sub(r'[._]', ' ', base)
        base = re.sub(r'\s+', ' ', base).strip()
        grouped.setdefault(base, []).append(f)

    for base_title, variants in sorted(grouped.items()):
        if len(variants) == 1:
            _add_video_item(variants[0], media_type, show_quality=False,
                            poster=poster, backdrop=backdrop)
        else:
            # Identicky s provider.py: slozka s variantami
            li = xbmcgui.ListItem(
                '[B]%s[/B]  [I](%d verzi)[/I]' % (base_title, len(variants)))
            if poster:
                li.setArt({'thumb': poster, 'poster': poster, 'fanart': backdrop or poster})
            xbmcplugin.addDirectoryItem(addon_handle,
                _url(mode='quality_select',
                     variants=json.dumps([{
                         'name': v['name'], 'ident': v['ident'],
                         'size': v.get('size_str', ''), 'size_b': str(v.get('size', 0)),
                         'positive': str(v.get('positive', 0)),
                         'negative': str(v.get('negative', 0)),
                         'desc': v.get('desc', ''),
                     } for v in variants]),
                     media_type=media_type, poster=poster, backdrop=backdrop),
                li, True)


def show_quality_select(variants_json, media_type='movie', poster='', backdrop=''):
    """Identicky s provider.py _show_quality_select() — serazeno podle velikosti."""
    xbmcplugin.setContent(addon_handle, 'videos')
    try:
        variants = json.loads(variants_json)
    except: variants = []
    # Seradit podle velikosti sestupne (jako parse_size_mb v provider.py)
    def _mb(v):
        try: return int(v.get('size_b', 0))
        except: return 0
    for v in sorted(variants, key=_mb, reverse=True):
        _add_video_item(v, media_type, show_quality=True, poster=poster, backdrop=backdrop)
    _end()


def _add_video_item(f, media_type, show_quality=False, poster='', backdrop=''):
    """Identicky s provider.py _add_video_item()."""
    name  = f.get('name', f.get('title', ''))
    ident = f.get('ident', '')
    size  = f.get('size_str', f.get('size', ''))
    plus  = f.get('positive', 0)
    minus = f.get('negative', 0)
    desc  = f.get('desc', '')

    # Label — identicky s provider.py
    if show_quality:
        label = name
    else:
        label = re.sub(r'\s+', ' ', re.sub(QUALITY_PATTERN, '', name, flags=re.I)).strip()
    label += '  [I][%s][/I]' % size
    if plus or minus:
        label += '  [I]+%s -%s[/I]' % (plus, minus)

    li = xbmcgui.ListItem(label)
    li.setProperty('IsPlayable', 'true')
    if poster:
        li.setArt({'thumb': poster, 'poster': poster, 'fanart': backdrop or poster})
    plot = ('%s\n\n' % desc if desc else '') + 'Velikost: %s  |  +%s -%s' % (size, plus, minus)
    _set_info(li, {'title': name, 'plot': plot,
                   'mediatype': 'movie' if media_type == 'movie' else 'episode'})

    # Context menu — identicky s provider.py
    li.addContextMenuItems([
        ('Pridat do Sledovanych',
         'RunPlugin(%s)' % _url(mode='add_watched', ident=ident,
                                title=name, size=size, media_type=media_type))
    ])

    xbmcplugin.addDirectoryItem(addon_handle,
        _url(mode='play', ident=ident, title=name), li, False)


# ══════════════════════════════════════════════════════════════════════════════
#  SELECT QUALITY (film z TMDB → WS search)
#  Identicky s workflow _show_tmdb_movie_item v provider.py
# ══════════════════════════════════════════════════════════════════════════════

def select_quality(title, year='', orig_title='', tmdb_id=''):
    token = _get_token()
    if not token: return _fail()

    prog = xbmcgui.DialogProgress()
    prog.create('Stream Cinema Caolina', 'Hledani: %s' % title)
    try:
        files = webshare.search_for_title(token, title, year=year,
                                          original_title=orig_title)
    except: files = []
    finally: prog.close()

    # Fallback — znovu po re-loginu
    if not files:
        token = _get_token(force=True)
        if token:
            try: files = webshare.search_for_title(token, title, year=year,
                                                    original_title=orig_title)
            except: files = []

    # Nacist poster z TMDB
    poster, backdrop = '', ''
    if tmdb_id and TMDB_KEY:
        try:
            det = tmdb_api.get_movie_details(TMDB_KEY, tmdb_id)
            poster   = det.get('poster', '')
            backdrop = det.get('backdrop', '')
        except: pass

    xbmcplugin.setContent(addon_handle, 'movies')

    if not files:
        li = xbmcgui.ListItem('[COLOR red]Neni k dispozici: %s[/COLOR]' % title)
        xbmcplugin.addDirectoryItem(addon_handle, '', li, False)
        return _end()

    _show_file_items(files, media_type='movie', poster=poster, backdrop=backdrop)
    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  SERIALY — identicky s provider.py _show_series_list()
# ══════════════════════════════════════════════════════════════════════════════

def show_series_list(serial_title, serial_year='', serial_original_name='',
                     tmdb_id='', num_seasons=0):
    """
    Zobrazí seznam sérií.
    TMDB se vyhledává OBĚMA názvy (EN orig + CZ), aby se správně identifikovalo
    tmdb_id a num_seasons. WS search pak vždy dostane EN orig_title.
    """
    xbmcplugin.setContent(addon_handle, 'tvshows')
    use_tmdb    = addon.getSetting('use_tmdb') != 'false'
    num_seasons = int(num_seasons) if num_seasons else 0

    # Doplnime TMDB data pokud chybi — hledáme OBĚMA názvy
    if use_tmdb and not (tmdb_id and num_seasons):
        orig = serial_original_name or serial_title
        cz   = serial_title

        # Kandidáti pro TMDB search: nejdřív EN orig, pak CZ (pokud se liší)
        candidates = [orig]
        if cz and _norm(cz) != _norm(orig):
            candidates.append(cz)

        for query in candidates:
            try:
                results = tmdb_api.search_tvshows(TMDB_KEY, query)
                if isinstance(results, tuple):
                    results = results[0]
                if results:
                    best      = results[0]
                    tmdb_id   = best.get('tmdb_id', best.get('id', ''))
                    # Aktualizuj orig_title z TMDB (EN) pro WS search
                    tmdb_orig = best.get('orig_title', '')
                    if tmdb_orig and not serial_original_name:
                        serial_original_name = tmdb_orig
                    elif tmdb_orig:
                        serial_original_name = tmdb_orig  # vždy přepiš EN originálem
                    if tmdb_id:
                        det = tmdb_api.get_tvshow_details(TMDB_KEY, tmdb_id)
                        if det:
                            num_seasons = det.get('seasons', det.get('number_of_seasons', 0))
                            # Také aktualizuj orig z detailu
                            if det.get('orig_title'):
                                serial_original_name = det['orig_title']
                if tmdb_id and num_seasons:
                    xbmc.log('SCC series_list: TMDB found "%s" (id=%s, seasons=%d) via query "%s"' % (
                        serial_original_name, tmdb_id, num_seasons, query), xbmc.LOGINFO)
                    break
            except Exception as e:
                xbmc.log('SCC series_list TMDB error: %s' % e, xbmc.LOGERROR)

    if use_tmdb and tmdb_id and num_seasons:
        found_seasons = list(range(1, int(num_seasons) + 1))
    else:
        # Fallback — detekce pres Webshare
        token = _get_token()
        if not token: return _fail()
        found_set   = set()
        # Hledej oběma názvy
        search_queries = []
        if serial_original_name:
            search_queries.append('%s S01' % serial_original_name)
        if serial_title and _norm(serial_title) != _norm(serial_original_name or ''):
            search_queries.append('%s S01' % serial_title)

        prog = xbmcgui.DialogProgress()
        prog.create('Stream Cinema Caolina', 'Detekuji serie: %s' % serial_title)
        try:
            for q in search_queries:
                try:
                    for f in webshare._raw_search(token, q, limit=50):
                        s = f.get('season')
                        if s: found_set.add(s)
                except: pass
            max_s = max(found_set) if found_set else 0
            search_base = serial_original_name or serial_title
            for s in range(1, max_s + 3):
                if s in found_set: continue
                try:
                    for f in webshare._raw_search(token, '%s S%02d' % (search_base, s), limit=20):
                        sn = f.get('season')
                        if sn: found_set.add(sn)
                except: pass
        finally:
            prog.close()
        found_seasons = sorted(found_set)

    if not found_seasons:
        return _fail('Serial nenalezen: %s' % serial_title)

    # Nacti poster
    poster = ''
    if tmdb_id and TMDB_KEY:
        try:
            det    = tmdb_api.get_tvshow_details(TMDB_KEY, tmdb_id)
            poster = det.get('poster', '') if det else ''
        except: pass

    xbmc.log('SCC series_list: %s / orig="%s" tmdb_id=%s seasons=%s' % (
        serial_title, serial_original_name, tmdb_id, found_seasons), xbmc.LOGINFO)

    for s in found_seasons:
        li = xbmcgui.ListItem('[B]Serie %d[/B]' % s)
        if poster:
            li.setArt({'thumb': poster, 'poster': poster, 'fanart': poster})
        xbmcplugin.addDirectoryItem(addon_handle,
            _url(mode='episodes', serial_title=serial_title,
                 serial_original_name=serial_original_name,
                 serial_year=serial_year, tmdb_id=tmdb_id, season=s),
            li, True)

    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  EPIZODY — identicky s provider.py _show_episodes()
# ══════════════════════════════════════════════════════════════════════════════

def show_episodes(serial_title, season, serial_year='',
                  serial_original_name='', tmdb_id=''):
    """
    Hledá epizody ve ČTYŘECH vlnách:
    1. EN originální název  (Stargate Atlantis S04)
    2. CZ název             (Hvězdná brána S04)
    3. Klíčové slovo z EN   (Atlantis S04)
    4. Klíčové slovo z CZ   (Hvezdna S04)
    Výsledky sloučí, vyfiltruje správnou sérii a seřadí do epizod.
    """
    xbmcplugin.setContent(addon_handle, 'episodes')
    season    = int(season)
    token     = _get_token()
    if not token: return _fail()

    orig_name = serial_original_name or serial_title   # EN: "Stargate Atlantis"
    cz_name   = serial_title                            # CZ: "Hvězdná brána"

    items    = []
    existing = set()

    def _merge(new_items):
        for ni in new_items:
            if ni['ident'] not in existing:
                items.append(ni)
                existing.add(ni['ident'])

    prog = xbmcgui.DialogProgress()
    prog.create('Stream Cinema Caolina',
                'Nacitam serie %d: %s' % (season, cz_name or orig_name))
    try:
        # === VLNA 1: EN originální název ===
        q1 = '%s S%02d' % (orig_name, season)
        xbmc.log('SCC episodes Q1 (EN): %s' % q1, xbmc.LOGINFO)
        _merge(webshare._raw_search(token, q1, limit=50))

        # === VLNA 2: CZ název (pokud se liší od EN) ===
        if cz_name and _norm(cz_name) != _norm(orig_name):
            q2 = '%s S%02d' % (cz_name, season)
            xbmc.log('SCC episodes Q2 (CZ): %s' % q2, xbmc.LOGINFO)
            _merge(webshare._raw_search(token, q2, limit=50))

        # === VLNA 3: Klíčové slovo z EN (Atlantis S04, Stargate S04) ===
        kw_en = _extract_keyword(orig_name)
        if kw_en and len(kw_en) > 4:
            q3 = '%s S%02d' % (kw_en, season)
            if _norm(q3) not in (_norm(q1),):
                xbmc.log('SCC episodes Q3 (kw_EN): %s' % q3, xbmc.LOGINFO)
                _merge(webshare._raw_search(token, q3, limit=30))

        # === VLNA 4: Klíčové slovo z CZ (Brana S04, Hvezdna S04) ===
        kw_cz = _extract_keyword(cz_name) if cz_name else ''
        if kw_cz and len(kw_cz) > 4 and _norm(kw_cz) != _norm(kw_en):
            q4 = '%s S%02d' % (kw_cz, season)
            xbmc.log('SCC episodes Q4 (kw_CZ): %s' % q4, xbmc.LOGINFO)
            _merge(webshare._raw_search(token, q4, limit=30))

    except Exception as e:
        xbmc.log('SCC episodes error: %s' % e, xbmc.LOGERROR)
    finally:
        prog.close()

    xbmc.log('SCC episodes raw: %d files for "%s"/"%s" S%02d' % (
        len(items), cz_name, orig_name, season), xbmc.LOGINFO)

    # Filtruj pouze epizody správné série — s kontrolou názvu
    filtered = _filter_season(items, season,
                               serial_title=cz_name,
                               serial_original_name=orig_name)
    xbmc.log('SCC episodes filtered: %d/%d' % (len(filtered), len(items)), xbmc.LOGINFO)

    if not filtered:
        return _fail('Zadne epizody pro: %s S%02d' % (cz_name, season))

    # Nacti nazvy a popisy epizod z TMDB (cs-CZ)
    ep_names, ep_plots = {}, {}
    if addon.getSetting('use_tmdb') != 'false' and tmdb_id and TMDB_KEY:
        try:
            season_data = tmdb_api.get_tv_season(TMDB_KEY, tmdb_id, season)
            for ep in (season_data.get('episodes') or []):
                n = ep.get('episode_number')
                if n is not None:
                    ep_names[n] = ep.get('name', '')
                    ep_plots[n] = ep.get('overview', '')
            xbmc.log('SCC TMDB ep names: %d entries for S%02d' % (len(ep_names), season), xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('SCC TMDB season error: %s' % e, xbmc.LOGERROR)

    # Seskupit podle cisla epizody, seradit varianty podle kvality
    groups = _group_by_episode(filtered)

    for ep_num in sorted(groups.keys()):
        variants = groups[ep_num]
        ep_label = 'S%02dE%02d' % (season, ep_num)
        ep_name  = ep_names.get(ep_num, '')
        ep_plot  = ep_plots.get(ep_num, '')

        folder_title = ('[B]%s  %s[/B]' % (ep_label, ep_name)
                        if ep_name else '[B]%s[/B]' % ep_label)

        li = xbmcgui.ListItem(folder_title)
        _set_info(li, {
            'title':     '%s - %s' % (ep_label, ep_name) if ep_name else ep_label,
            'season':    season,
            'episode':   ep_num,
            'plot':      ep_plot or '',
            'mediatype': 'episode',
        })

        xbmcplugin.addDirectoryItem(addon_handle,
            _url(mode='episode_variants',
                 variants=json.dumps([{
                     'name':     v['name'],
                     'ident':    v['ident'],
                     'size':     v.get('size_str', ''),
                     'size_b':   str(v.get('size', 0)),
                     'positive': str(v.get('positive', 0)),
                     'negative': str(v.get('negative', 0)),
                     'desc':     v.get('desc', ''),
                 } for v in variants]),
                 season=season, ep_num=ep_num,
                 ep_name=ep_name, ep_plot=ep_plot),
            li, True)

    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  VARIANTY EPIZODY — identicky s provider.py _show_episode_variants()
# ══════════════════════════════════════════════════════════════════════════════

def show_episode_variants(variants_json, season, ep_num, ep_name='', ep_plot=''):
    """Identicky s provider.py _show_episode_variants()."""
    xbmcplugin.setContent(addon_handle, 'episodes')
    season = int(season)
    ep_num = int(ep_num)

    try: variants = json.loads(variants_json)
    except: variants = []

    ep_label = 'S%02dE%02d' % (season, ep_num)

    for v in variants:
        name  = v.get('name', '')
        ident = v.get('ident', '')
        size  = v.get('size', '')
        plus  = v.get('positive', 0)
        minus = v.get('negative', 0)
        desc  = v.get('desc', '')

        # Parsuj kvalitu a jazyk — identicky s parse_quality/parse_language v provider.py
        q_label, q_rank = _parse_quality(name)
        lang             = _parse_language(name)

        # Label — identicky s provider.py: "1080p  |  CZ+EN  |  4.20 GB"
        info_parts = [q_label] if q_label else []
        if lang:
            info_parts.append(lang)
        if size:
            info_parts.append(size)
        info_str = '  |  '.join(filter(None, info_parts)) or name

        # Nejlepsi kvalita tucne — identicky s provider.py (q_key >= 80)
        label = ('[B]%s[/B]' % info_str if q_rank >= 80 else info_str)

        # Plot — identicky s provider.py
        plot_parts = []
        if ep_name:  plot_parts.append(ep_name)
        if ep_plot:  plot_parts.append(ep_plot)
        if desc:     plot_parts.append(desc)
        if size:     plot_parts.append('Velikost: %s' % size)
        plot = '\n\n'.join(filter(None, plot_parts))

        li = xbmcgui.ListItem(label)
        li.setProperty('IsPlayable', 'true')
        info = {
            'title':   name, 'season': season, 'episode': ep_num,
            'plot':    plot, 'mediatype': 'episode',
        }
        if ep_name:
            info['episodename'] = ep_name
        _set_info(li, info)

        # Context menu — identicky s provider.py
        li.addContextMenuItems([
            ('Pridat do Sledovanych',
             'RunPlugin(%s)' % _url(mode='add_watched', ident=ident,
                                    title=name, size=size, media_type='tvshow'))
        ])

        xbmcplugin.addDirectoryItem(addon_handle,
            _url(mode='play', ident=ident, title=name), li, False)

    _end()


# ══════════════════════════════════════════════════════════════════════════════
#  FILTROVANI / PARSOVANI — ekvivalent file_filter.py z provider.py
# ══════════════════════════════════════════════════════════════════════════════

def _filter_season(files, season, serial_title='', serial_original_name=''):
    """
    Filtruje soubory na danou sezónu A správný seriál.
    Dvojitá kontrola: číslo sezóny + shoda názvu seriálu.
    Zabraňuje: "Hvězdná brána S01" → soubory z Red Dwarf S01
    """
    import unicodedata

    def _norm_title(s):
        try:
            n = unicodedata.normalize('NFD', s or '')
            return re.sub(r'\s+', ' ',
                   re.sub(r'[._\-]', ' ',
                   ''.join(c for c in n if unicodedata.category(c) != 'Mn'))
                   ).lower().strip()
        except:
            return (s or '').lower().strip()

    def _title_ok(filename):
        """Zkontroluje jestli název souboru odpovídá seriálu."""
        fn = _norm_title(filename)
        # Stačí shoda s jedním z názvů (EN nebo CZ)
        for t in [serial_original_name, serial_title]:
            if not t:
                continue
            nt = _norm_title(t)
            # Celý název je obsažen
            if nt and nt in fn:
                return True
            # Všechna slova > 2 znaky jsou obsažena
            words = [w for w in nt.split() if len(w) > 2]
            if words:
                hits = sum(1 for w in words
                           if re.search(r'\b' + re.escape(w) + r'\b', fn))
                if len(words) == 1 and hits == 1:
                    return True
                if len(words) == 2 and hits == 2:
                    return True
                if len(words) > 2 and hits / float(len(words)) >= 0.85:
                    return True
        # Pokud nemáme žádný název k porovnání, přijmeme soubor
        return not (serial_title or serial_original_name)

    result = []
    for f in files:
        fs = f.get('season')   # int nebo None z parse_filename()
        fe = f.get('episode')
        name = f.get('name', '')

        # Kontrola sezóny
        season_ok = False
        if fs is not None:
            if fs == season and fe is not None:
                season_ok = True
        else:
            m = re.search(r'(?i)[Ss](\d{1,2})[Ee]\d{1,2}', name)
            if m and int(m.group(1)) == season:
                season_ok = True
            else:
                m = re.search(r'\b(\d{1,2})[xX](\d{2})\b', name)
                if m and int(m.group(1)) == season:
                    season_ok = True

        if not season_ok:
            continue

        # Kontrola názvu seriálu — zabrání průniku jiných seriálů
        if not _title_ok(name):
            xbmc.log('SCC filter: zamitnuto (jiny serial) [%s]' % name, xbmc.LOGDEBUG)
            continue

        result.append(f)

    return result


def _group_by_episode(files):
    """
    Seskupi soubory podle cisla epizody.
    Podporuje: S04E06, S04E06E07 (multi), 4x06
    Seřadí varianty: nejlepší kvalita první.
    """
    groups = {}
    for f in files:
        ep = f.get('episode')  # z parse_filename() — int nebo None

        if ep is None:
            name = f.get('name', '')
            # S04E06 nebo S04E06E07
            m = re.search(r'(?i)[Ss]\d{1,2}[Ee](\d{1,2})', name)
            if m:
                ep = int(m.group(1))
            else:
                # 4x06
                m = re.search(r'\b\d{1,2}[xX](\d{2})\b', name)
                ep = int(m.group(1)) if m else 0

        groups.setdefault(int(ep), []).append(f)

    # Seradit varianty: nejlepsi kvalita první (rank ASC), pak velikost DESC
    for ep in groups:
        groups[ep].sort(key=lambda x: (x.get('quality_rank', 99), -x.get('size', 0)))
    return groups


def _extract_keyword(title):
    """
    Nejdelsi slovo z nazvu (ekvivalent _extract_keywords() z provider.py).
    Pouziva se jako fallback query pro WS search.
    """
    words = [w for w in re.split(r'\W+', title) if len(w) > 3]
    return max(words, key=len) if words else ''


def _parse_quality(name):
    """
    Vraci (label, rank) — ekvivalent parse_quality() z provider.py.
    rank: 100=4K, 80=1080p, 60=720p, 40=SD, 20=nizka
    """
    n = name.upper()
    if re.search(r'(4K|2160P|UHD)', n):   return '4K',    100
    if re.search(r'1080P', n):             return '1080p',  80
    if re.search(r'720P', n):              return '720p',   60
    if re.search(r'(480P|576P|DVDRIP)', n):return 'SD',     40
    if re.search(r'(CAM|CAMRIP|TS\b)', n): return 'CAM',   20
    return '', 50


def _parse_language(name):
    """
    Vraci jazykovy retezec (CZ, SK, EN, CZ+SK, atd.).
    Ekvivalent parse_language() z provider.py.
    """
    n = name.upper()
    langs = []
    if re.search(r'\bCZ[\. \-_]?(DUB|DAB|DABING|TITULKY)?\b', n): langs.append('CZ')
    if re.search(r'\bSK[\. \-_]?(DUB|DAB|DABING|TITULKY)?\b', n): langs.append('SK')
    if re.search(r'\b(ENG|EN|ENGLISH)\b', n): langs.append('EN')
    return '+'.join(langs) if langs else ''


# ══════════════════════════════════════════════════════════════════════════════
#  ABECEDA
# ══════════════════════════════════════════════════════════════════════════════

def alphabet_root(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    letters = (list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') +
               [u'\xc1',u'\u010c',u'\u010e',u'\xc9',u'\u011a',u'\xcd',
                u'\u0147',u'\xd3',u'\u0158',u'\u0160',u'\u0164',u'\xda',
                u'\u016e',u'\xdd',u'\u017d'] +
               list('0123456789'))
    for letter in letters:
        _add_dir('[B]%s[/B]' % letter,
                 _url(mode='alphabet_search', prefix=letter, media_type=media_type))
    _end()


def alphabet_search(prefix, media_type='movie'):
    if addon.getSetting('use_tmdb') != 'false':
        if media_type == 'tvshow':
            _search_series_with_tmdb(prefix)
        else:
            _search_movies_with_tmdb(prefix, page=1)
    else:
        _do_search_files(prefix, media_type=media_type)


# ══════════════════════════════════════════════════════════════════════════════
#  NAPOSLEDY SLEDOVANE — identicky s show_watched_items() z provider.py
# ══════════════════════════════════════════════════════════════════════════════

def show_watched_list(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    watched = _load_watched()
    items = {k: v for k, v in watched.items()
             if v.get('media_type') == media_type}

    if not items:
        _notify('Zadne sledovane polozky')
        return _fail()

    for ident, data in sorted(items.items(),
                               key=lambda i: i[1]['time'], reverse=True):
        label = data['title'] + '  [I][%s][/I]' % data.get('size', '')
        li = xbmcgui.ListItem(label)
        li.setProperty('IsPlayable', 'true')
        if data.get('img'):
            li.setArt({'thumb': data['img']})
        # Context menu: odebrat — identicky s provider.py
        li.addContextMenuItems([
            ('Odebrat ze Sledovanych',
             'RunPlugin(%s)' % _url(mode='remove_watched', ident=ident))
        ])
        xbmcplugin.addDirectoryItem(addon_handle,
            _url(mode='play', ident=ident, title=data['title']), li, False)
    _end()


def watched_add(ident, title, size='', img='', media_type='movie'):
    """Identicky s _add_watched() z provider.py."""
    watched = _load_watched()
    watched[ident] = {
        'title': title, 'size': size, 'img': img,
        'time': int(_time_mod.time()), 'media_type': media_type,
    }
    _save_watched(_trim_watched(watched))
    _notify('Pridano do Sledovanych')


def watched_remove(ident):
    """Identicky s _remove_watched() z provider.py."""
    watched = _load_watched()
    if ident in watched:
        del watched[ident]
        _save_watched(watched)
    _notify('Odebrano. Zmena se projevi po dalsim otevreni.')
    xbmc.executebuiltin('Container.Refresh')


def _auto_watched(ident, title, size='', img='', media_type='movie'):
    """Identicky s _auto_watched() z provider.py — automaticky po prehrani."""
    watched = _load_watched()
    watched[ident] = {
        'title': title, 'size': size, 'img': img,
        'time': int(_time_mod.time()), 'media_type': media_type,
    }
    _save_watched(_trim_watched(watched))


# ══════════════════════════════════════════════════════════════════════════════
#  PREHRAVANI — identicky s resolve() z provider.py
# ══════════════════════════════════════════════════════════════════════════════

def play_file(ident, title=''):
    """Identicky s resolve() z provider.py."""
    token = _get_token()
    if not token:
        xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
        return

    link = webshare.get_file_link(token, ident)
    if not link:
        # Re-login a zkus znovu
        token = _get_token(force=True)
        if token:
            link = webshare.get_file_link(token, ident)

    if not link:
        _notify('Nelze ziskat odkaz. Zkontrolujte Webshare VIP ucet.',
                xbmcgui.NOTIFICATION_ERROR, 5000)
        xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
        return

    li = xbmcgui.ListItem(title, path=link)
    li.setProperty('IsPlayable', 'true')
    # MIME type podle pripony
    ext = (title or '').lower().rsplit('.', 1)[-1]
    mime_map = {'mkv': 'video/x-matroska', 'mp4': 'video/mp4', 'm4v': 'video/mp4',
                'avi': 'video/avi', 'ts': 'video/mp2t', 'm2ts': 'video/mp2t'}
    li.setMimeType(mime_map.get(ext, 'video/x-matroska'))
    li.setContentLookup(False)
    xbmcplugin.setResolvedUrl(addon_handle, True, li)
    _auto_watched(ident, title)


def show_donation():
    """Zobrazí QR kód a text s poděkováním pro dobrovolný příspěvek."""
    import os as _os
    qr_path = _os.path.join(
        _translate_path(addon.getAddonInfo('path')),
        'resources', 'qr_donation.jpg'
    )

    # Zobraz QR kód přes Kodi image viewer
    if _os.path.exists(qr_path):
        xbmc.executebuiltin('ShowPicture(%s)' % qr_path)
        xbmc.sleep(300)  # krátká pauza aby se obrázek otevřel

    # Text dialog s poděkováním
    xbmcgui.Dialog().ok(
        u'[COLOR gold]♥  Podpora vývoje  —  Stream Cinema Caolina[/COLOR]',
        u'[B]Díky za používání Stream Cinema Caolina![/B]\n\n'
        u'Doplněk vyvíjím ve volném čase a zdarma pro všechny.\n'
        u'Pokud ti šetří čas a přináší radost ze sledování,\n'
        u'budu rád za dobrovolný příspěvek na další vývoj.\n\n'
        u'[COLOR gold]► Platba QR kódem:  20 Kč[/COLOR]\n'
        u'   (nebo libovolná částka dle uvážení)\n\n'
        u'QR kód byl zobrazen v prohlížeči obrázků.\n'
        u'Naskenuj ho mobilem a hotovo. Mockrát díky! ♥'
    )
    _fail()


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def router(params):
    mode = params.get('mode')

    if   mode is None:               main_menu()
    elif mode == 'media_root':       media_root(params.get('media_type', 'movie'))
    elif mode == 'search':           do_search(params.get('search_id', ''))
    elif mode == 'search_more':      search_more(params.get('keyword', ''),
                                                 params.get('search_id', 'movie'),
                                                 int(params.get('page', 1)))
    elif mode == 'genre_list':       show_genre_list(params.get('media_type', 'movie'))
    elif mode == 'genre_movies':     show_genre_movies(
                                         params.get('genre_id', ''),
                                         params.get('genre_name', ''),
                                         params.get('media_type', 'movie'),
                                         int(params.get('page', 1)))
    elif mode == 'country_list':     show_country_list(params.get('media_type', 'movie'))
    elif mode == 'country_movies':   show_country_movies(
                                         params.get('country_code', ''),
                                         params.get('country_name', ''),
                                         params.get('media_type', 'movie'),
                                         int(params.get('page', 1)))
    elif mode == 'trending_movies':  show_trending_movies()
    elif mode == 'popular_movies':   show_popular_movies(int(params.get('page', 1)))
    elif mode == 'select_quality':   select_quality(
                                         params.get('title', ''),
                                         params.get('year', ''),
                                         params.get('orig_title', ''),
                                         params.get('tmdb_id', ''))
    elif mode == 'quality_select':   show_quality_select(
                                         params.get('variants', '[]'),
                                         params.get('media_type', 'movie'),
                                         params.get('poster', ''),
                                         params.get('backdrop', ''))
    elif mode == 'series_list':      show_series_list(
                                         params.get('serial_title', ''),
                                         params.get('serial_year', ''),
                                         params.get('serial_original_name', ''),
                                         params.get('tmdb_id', ''),
                                         params.get('num_seasons', 0))
    elif mode == 'episodes':         show_episodes(
                                         params.get('serial_title', ''),
                                         params.get('season', 1),
                                         params.get('serial_year', ''),
                                         params.get('serial_original_name', ''),
                                         params.get('tmdb_id', ''))
    elif mode == 'episode_variants': show_episode_variants(
                                         params.get('variants', '[]'),
                                         params.get('season', 1),
                                         params.get('ep_num', 1),
                                         params.get('ep_name', ''),
                                         params.get('ep_plot', ''))
    elif mode == 'alphabet_root':    alphabet_root(params.get('media_type', 'movie'))
    elif mode == 'alphabet_search':  alphabet_search(params.get('prefix', 'A'),
                                                     params.get('media_type', 'movie'))
    elif mode == 'watched_list':     show_watched_list(params.get('media_type', 'movie'))
    elif mode == 'add_watched':      watched_add(
                                         params.get('ident', ''),
                                         params.get('title', ''),
                                         params.get('size', ''),
                                         media_type=params.get('media_type', 'movie'))
    elif mode == 'remove_watched':   watched_remove(params.get('ident', ''))
    elif mode == 'play':             play_file(params.get('ident', ''),
                                               params.get('title', ''))
    elif mode == 'account_info':     show_account_info()
    elif mode == 'do_login':         do_login()
    elif mode == 'donation':         show_donation()
    elif mode == 'settings':         addon.openSettings(); _fail()
    else:                            main_menu()
