# -*- coding: utf-8 -*-
"""
Webshare.cz API — Stream Cinema Caolina
Login přesně dle funkčních pluginů yawsp/wsc/kodi-czsk:
  password = SHA1( md5crypt(password, salt) ).hexdigest()
  digest   = MD5( username + ':Webshare:' + PŮVODNÍ_heslo ).hexdigest()
"""

import re
import hashlib
import unicodedata
import xbmc

try:
    from urllib.request import urlopen, Request
    from urllib.parse import urlencode
except ImportError:
    from urllib2 import urlopen, Request
    from urllib import urlencode

from md5crypt import md5crypt

WEBSHARE_API = 'https://webshare.cz/api'

VIDEO_EXTS = {
    '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.m4v',
    '.ts', '.m2ts', '.flv', '.ogm', '.webm', '.rmvb',
}

MIN_SIZE_MOVIE   = 200 * 1024 * 1024  # 200 MB
MIN_SIZE_EPISODE = 100 * 1024 * 1024  # 100 MB

# ─────────────────────────────────────────────────────────
#  PTT-inspired parser
# ─────────────────────────────────────────────────────────

QUALITY_MAP = [
    (r'(?i)\b(4k|2160p|uhd)\b',        '4K',     1),
    (r'(?i)\b1080p\b',                  '1080p',  2),
    (r'(?i)\b(bluray|blu-ray|bdrip)\b', 'BluRay', 2),
    (r'(?i)\b(webdl|web-dl)\b',         'WEB-DL', 2),
    (r'(?i)\b(webrip|web-rip)\b',       'WEBRip', 3),
    (r'(?i)\b1080i\b',                  '1080i',  3),
    (r'(?i)\b720p\b',                   '720p',   4),
    (r'(?i)\b(hdtv|hdtvrip)\b',         'HDTV',   4),
    (r'(?i)\b480p\b',                   '480p',   5),
    (r'(?i)\b(576p|dvdrip)\b',          'DVDRip', 6),
    (r'(?i)\b(xvid|divx)\b',            'DVDRip', 6),
    (r'(?i)\b(dvdscr|scr)\b',           'DVDScr', 7),
    (r'(?i)\b(telesync)\b',             'TS',     8),
    (r'(?i)\b(cam|camrip|hdcam)\b',     'CAM',    9),
]

LANG_MAP = [
    (r'(?i)\bcz[\. _\-]?dub(bing)?\b',          'CZ dabing'),
    (r'(?i)\b(czech|cestina|cesky)\b',           'CZ'),
    (r'(?i)(^|[\.\- _(])cz([\.\- _)|$])',        'CZ'),
    (r'(?i)\bsk[\. _\-]?dub(bing)?\b',           'SK dabing'),
    (r'(?i)\b(slovak|slovencina|slovensky)\b',   'SK'),
    (r'(?i)(^|[\.\- _(])sk([\.\- _)|$])',        'SK'),
    (r'(?i)\b(eng|english)\b',                   'EN'),
    (r'(?i)(^|[\.\- _(])en([\.\- _)|$])',        'EN'),
    (r'(?i)\b(ger|german|deutsch)\b',            'DE'),
    (r'(?i)\b(pol|polish|polski)\b',             'PL'),
    (r'(?i)\b(hun|hungarian|magyar)\b',          'HU'),
    (r'(?i)\b(rus|russian)\b',                   'RU'),
    (r'(?i)\b(multi|multilang|multisub)\b',      'MULTI'),
    (r'(?i)\b(titulky|subtitles?|subs?)\b',      'titulky'),
]

AUDIO_MAP = [
    (r'(?i)\b(dolby.?atmos|atmos)\b',       'Atmos'),
    (r'(?i)\b(dts.?hd.?ma|dts.?ma)\b',      'DTS-HD MA'),
    (r'(?i)\b(dts.?hd)\b',                  'DTS-HD'),
    (r'(?i)\b(dts)\b',                       'DTS'),
    (r'(?i)\b(truehd)\b',                    'TrueHD'),
    (r'(?i)\b(dd5\.?1|ac3|dolby.digital)\b', 'DD5.1'),
    (r'(?i)\b(aac)\b',                       'AAC'),
    (r'(?i)\b(mp3)\b',                       'MP3'),
]

CODEC_MAP = [
    (r'(?i)\b(x265|h\.?265|hevc)\b', 'H.265'),
    (r'(?i)\b(x264|h\.?264|avc)\b',  'H.264'),
    (r'(?i)\b(av1)\b',               'AV1'),
    (r'(?i)\b(xvid)\b',              'XviD'),
    (r'(?i)\b(divx)\b',              'DivX'),
]


def parse_filename(name):
    info = {
        'quality': '', 'quality_rank': 99,
        'langs': [], 'audio': [], 'codec': '',
        'year': '', 'season': None, 'episode': None,
    }
    for pat, lbl, rank in QUALITY_MAP:
        if re.search(pat, name):
            if rank < info['quality_rank']:
                info['quality'] = lbl
                info['quality_rank'] = rank
    for pat, lbl in LANG_MAP:
        if re.search(pat, name) and lbl not in info['langs']:
            info['langs'].append(lbl)
    for pat, lbl in AUDIO_MAP:
        if re.search(pat, name) and lbl not in info['audio']:
            info['audio'].append(lbl)
    for pat, lbl in CODEC_MAP:
        if re.search(pat, name):
            info['codec'] = lbl
            break
    m = re.search(r'\b(19\d{2}|20\d{2})\b', name)
    if m:
        info['year'] = m.group(1)
    # Epizody: S01E01 > 1x01 > E05/ep05
    m = re.search(r'(?i)[Ss](\d{1,2})[Ee](\d{1,2})', name)
    if m:
        info['season'] = int(m.group(1))
        info['episode'] = int(m.group(2))
    else:
        m = re.search(r'(?i)(\d{1,2})x(\d{1,2})', name)
        if m:
            info['season'] = int(m.group(1))
            info['episode'] = int(m.group(2))
        else:
            m = re.search(r'(?i)\b[Ee]p?[\. _]?(\d{1,2})\b', name)
            if m:
                info['episode'] = int(m.group(1))
    return info


def _norm(s):
    try:
        if isinstance(s, bytes):
            s = s.decode('utf-8')
        n = unicodedata.normalize('NFD', s)
        out = u''.join(c for c in n if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^a-z0-9 ]', ' ', out.lower()).strip()
    except Exception:
        return s.lower()


def _title_matches(title, filename):
    """
    Přísné porovnání názvu titulu s názvem souboru.

    - Normalizuje diakritiku, tečky/pomlčky → mezery
    - Porovnává pouze "title část" souboru (před SxxExx nebo rokem)
    - Jednoslovný název: nesmí být jen začátek delšího titulu
      ('Avatar' ≠ 'Avatar.The.Last.Airbender')
    - Dvouslovný název: OBA klíčová slova musí být přítomna
    - Víceslovný název: 85%+ klíčových slov musí být přítomno
    """
    def _nfn(s):
        try:
            n = unicodedata.normalize('NFD', str(s))
            n = u''.join(c for c in n if unicodedata.category(c) != 'Mn').lower()
            return re.sub(r'\s+', ' ', re.sub(r'[._\-]', ' ', n)).strip()
        except:
            return str(s).lower().strip()

    fn = _nfn(filename)
    t  = _nfn(title)

    if not t or not fn:
        return False
    if t == fn:
        return True

    # Část souboru před S01E01 nebo rokem = skutečný název titulu
    ep_m = re.search(r'\b[Ss]\d{1,2}[Ee]\d{1,2}\b|\b(19|20)\d{2}\b', fn)
    fn_title = fn[:ep_m.start()].strip() if ep_m else fn

    t_words = t.split()
    if not t_words:
        return False

    if len(t_words) == 1:
        w = t_words[0]
        stop = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or', 'but'}
        fn_content = [x for x in fn_title.split() if x not in stop]
        # Pokud soubor začíná naším slovem ale má 2+ dalších slov → jiný (delší) titul
        if fn_content and fn_content[0] == w and len(fn_content) > 2:
            return False
        return bool(re.search(r'\b' + re.escape(w) + r'\b', fn_title))

    key_words = [w for w in t_words if len(w) > 2]
    if not key_words:
        return False

    hits = sum(1 for w in key_words
               if re.search(r'\b' + re.escape(w) + r'\b', fn))

    if len(key_words) == 2:
        return hits == 2
    return hits / float(len(key_words)) >= 0.85


def format_size(b):
    try:
        b = int(b)
    except (ValueError, TypeError):
        return ''
    if b >= 1024**3:
        return '%.1f GB' % (b / 1024.0**3)
    if b >= 1024**2:
        return '%.0f MB' % (b / 1024.0**2)
    return '%.0f KB' % (b / 1024.0)


def build_file_label(name, size_bytes, positive=0):
    info = parse_filename(name)
    parts = []
    if info['quality']:
        parts.append('[COLOR yellow][%s][/COLOR]' % info['quality'])
    if info['langs']:
        parts.append('[COLOR cyan][%s][/COLOR]' % ' | '.join(info['langs']))
    if info['audio']:
        parts.append('[COLOR green][%s][/COLOR]' % ' | '.join(info['audio']))
    if info['codec']:
        parts.append('[COLOR gray][%s][/COLOR]' % info['codec'])
    label = '  '.join(parts) if parts else name
    sz = format_size(size_bytes)
    if sz:
        label += '  [COLOR white]%s[/COLOR]' % sz
    if positive and int(positive) > 0:
        label += '  [COLOR orange]♥%d[/COLOR]' % int(positive)
    return label


# ─────────────────────────────────────────────────────────
#  Webshare API
# ─────────────────────────────────────────────────────────

def _post(endpoint, data, token=None):
    url = '%s/%s/' % (WEBSHARE_API, endpoint)
    if token:
        data['wst'] = token
    try:
        body = urlencode(data)
        if isinstance(body, str):
            body = body.encode('utf-8')
        req = Request(url, body, {
            'Content-Type':     'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept':           'text/xml; charset=UTF-8',
        })
        return urlopen(req, timeout=15).read().decode('utf-8')
    except Exception as e:
        xbmc.log('WS [%s] error: %s' % (endpoint, e), xbmc.LOGERROR)
        return ''


def _x(xml, tag):
    m = re.search(r'<%s>(.*?)</%s>' % (tag, tag), xml, re.DOTALL)
    return m.group(1).strip() if m else ''


# ─────────────────────────────────────────────────────────
#  LOGIN — přesně dle kodi-czsk/yawsp/wsc
# ─────────────────────────────────────────────────────────

def login(username, password):
    """
    Přihlásí se k Webshare.cz.

    Přesný postup dle funkčních pluginů (kodi-czsk, yawsp, wsc):
      1. Získej salt z API
      2. password_hash = SHA1( md5crypt(password, salt) ).hexdigest()
      3. digest = MD5( username + ':Webshare:' + PŮVODNÍ_heslo ).hexdigest()
      4. Pošli login s oběma

    KLÍČOVÝ DETAIL: digest se počítá z PŮVODNÍHO hesla, ne z hashe!
    """
    # 1. Získej salt
    xml = _post('salt', {'username_or_email': username})
    if not xml:
        xbmc.log('WS login: žádná odpověď pro salt', xbmc.LOGERROR)
        return None
    if _x(xml, 'status') != 'OK':
        xbmc.log('WS login: salt status=%s msg=%s' % (_x(xml, 'status'), _x(xml, 'message')), xbmc.LOGERROR)
        return None

    salt = _x(xml, 'salt')
    if not salt:
        xbmc.log('WS login: prázdný salt', xbmc.LOGERROR)
        return None

    xbmc.log('WS: salt OK = "%s"' % salt, xbmc.LOGDEBUG)

    # 2. Hash hesla: SHA1( md5crypt(password, salt).encode('utf-8') )
    # md5crypt vraci STRING "$1$salt$hash" — stejne jako SCC unix_md5_crypt
    # SHA1 se pocita z UTF-8 encoded stringu — identicky s SCC kodiutils.hash_password
    try:
        crypt_str     = md5crypt(password, salt)  # returns STRING
        password_hash = hashlib.sha1(crypt_str.encode('utf-8')).hexdigest()
    except Exception as e:
        xbmc.log('WS: chyba pri hashovani hesla: %s' % e, xbmc.LOGERROR)
        return None

    # 3. Digest: MD5(username + ':Webshare:' + PŮVODNÍ heslo)
    #    POZOR: používáme PŮVODNÍ heslo, ne zahashované!
    try:
        digest_str = '%s:Webshare:%s' % (username, password)
        digest = hashlib.md5(digest_str.encode('utf-8')).hexdigest()
    except Exception as e:
        xbmc.log('WS: chyba při digest: %s' % e, xbmc.LOGERROR)
        return None

    xbmc.log('WS: hash OK, odesílám login...', xbmc.LOGDEBUG)

    # 4. Login
    xml = _post('login', {
        'username_or_email': username,
        'password':          password_hash,
        'digest':            digest,
        'keep_logged_in':    1,
    })

    if not xml:
        xbmc.log('WS login: žádná odpověď', xbmc.LOGERROR)
        return None
    if _x(xml, 'status') != 'OK':
        msg = _x(xml, 'message')
        xbmc.log('WS login FAILED: %s' % msg, xbmc.LOGERROR)
        return None

    token = _x(xml, 'token')
    if not token:
        xbmc.log('WS login: prázdný token', xbmc.LOGERROR)
        return None

    xbmc.log('WS: přihlášení OK, token=%s...' % token[:10], xbmc.LOGDEBUG)
    return token


# ─────────────────────────────────────────────────────────
#  Raw search
# ─────────────────────────────────────────────────────────

def _raw_search(token, query, limit=50, sort='best'):
    xml = _post('search', {
        'what':     query,
        'category': 'video',
        'sort':     sort,
        'limit':    limit,
        'offset':   0,
    }, token=token)

    if not xml or _x(xml, 'status') != 'OK':
        return []

    files = []
    for block in re.findall(r'<file>(.*?)</file>', xml, re.DOTALL):
        ident = _x(block, 'ident')
        name  = _x(block, 'name')
        if not ident or not name:
            continue
        if _x(block, 'password') == '1':
            continue
        ext = ('.' + name.rsplit('.', 1)[-1]).lower() if '.' in name else ''
        if ext not in VIDEO_EXTS:
            continue
        sz_s = _x(block, 'size')
        sz   = int(sz_s) if sz_s.isdigit() else 0
        pos  = _x(block, 'positive')
        neg  = _x(block, 'negative')
        fi   = parse_filename(name)
        fi.update({
            'ident':    ident,
            'name':     name,
            'size':     sz,
            'size_str': format_size(sz),
            'positive': int(pos) if pos.isdigit() else 0,
            'negative': int(neg) if neg.isdigit() else 0,
        })
        files.append(fi)
    return files


# ─────────────────────────────────────────────────────────
#  Smart search — Krok A (dotazy) + Krok B (The Bouncer)
# ─────────────────────────────────────────────────────────

def _build_queries(title, year='', original_title=''):
    queries = []
    if year:
        queries.append('%s %s' % (title, year))
    queries.append(title)
    if original_title and original_title.lower() != title.lower():
        if year:
            queries.append('%s %s' % (original_title, year))
        queries.append(original_title)
    clean = _norm(title).title()
    if clean.lower() != title.lower():
        if year:
            queries.append('%s %s' % (clean, year))
    return queries[:4]


def _bouncer(files, titles, year, min_size):
    good = []
    for f in files:
        if f['size'] < min_size:
            continue
        if not any(_title_matches(t, f['name']) for t in titles):
            xbmc.log('WS filter: neshoda názvu [%s]' % f['name'], xbmc.LOGDEBUG)
            continue
        if year and f.get('year') and f['year'] != str(year):
            xbmc.log('WS filter: špatný rok %s!=%s [%s]' % (f['year'], year, f['name']), xbmc.LOGDEBUG)
            continue
        good.append(f)
    return good


def _sort_files(files):
    files.sort(key=lambda x: (x.get('quality_rank', 99), -x.get('size', 0)))
    return files


def search_for_title(token, title, year='', original_title='', limit=50):
    """
    Hledá filmy na Webshare podle názvu.
    Spustí více dotazů (CZ + EN + rok), výsledky sloučí a přefiltruje.
    """
    all_files = {}
    for q in _build_queries(title, year, original_title):
        try:
            for f in _raw_search(token, q, limit=limit):
                if f['ident'] not in all_files:
                    all_files[f['ident']] = f
        except Exception as e:
            xbmc.log('WS search [%s]: %s' % (q, e), xbmc.LOGERROR)

    if not all_files:
        return []

    xbmc.log('WS search_for_title: %d raw results for "%s" / "%s"' % (
        len(all_files), title, original_title), xbmc.LOGINFO)

    # Všechny varianty názvů pro matching (CZ + EN)
    titles = [title]
    if original_title and _norm(original_title) != _norm(title):
        titles.append(original_title)

    # Krok 1: přísný filtr — název + rok + min. velikost
    filtered = _bouncer(list(all_files.values()), titles, year, MIN_SIZE_MOVIE)

    # Krok 2: bez omezení velikosti
    if not filtered:
        filtered = _bouncer(list(all_files.values()), titles, year, min_size=0)
        if filtered:
            xbmc.log('WS search_for_title: fallback bez min_size, %d vysledku' % len(filtered), xbmc.LOGINFO)

    # Krok 3: bez roku (rok mohl být špatně parsován)
    if not filtered:
        filtered = _bouncer(list(all_files.values()), titles, year='', min_size=0)
        if filtered:
            xbmc.log('WS search_for_title: fallback bez roku, %d vysledku' % len(filtered), xbmc.LOGINFO)

    if not filtered:
        xbmc.log('WS search_for_title: 0 vysledku po filtru pro "%s"' % title, xbmc.LOGWARNING)
        return []

    xbmc.log('WS search_for_title: %d/%d po filtru pro "%s"' % (
        len(filtered), len(all_files), title), xbmc.LOGINFO)
    return _sort_files(filtered)


def search_for_episode(token, title, season, episode, year='', original_title='', limit=50):
    all_files = {}
    s_str = 'S%02dE%02d' % (season, episode)
    x_str = '%dx%02d'    % (season, episode)

    base_titles = [title]
    if original_title and original_title.lower() != title.lower():
        base_titles.append(original_title)

    for t in base_titles[:2]:
        for marker in [s_str, x_str]:
            q = '%s %s' % (t, marker)
            try:
                for f in _raw_search(token, q, limit=limit):
                    if f['ident'] not in all_files:
                        all_files[f['ident']] = f
            except Exception as e:
                xbmc.log('WS ep search [%s]: %s' % (q, e), xbmc.LOGERROR)

    if not all_files:
        return []

    filtered = []
    for f in all_files.values():
        if f['size'] < MIN_SIZE_EPISODE:
            continue
        fs = f.get('season')
        fe = f.get('episode')
        if fs is not None and fs != season:
            continue
        if fe is not None and fe != episode:
            continue
        if fs is None and fe is None:
            if not (re.search(r'(?i)[Ss]%02d[Ee]%02d' % (season, episode), f['name']) or
                    re.search(r'(?i)%dx%02d' % (season, episode), f['name'])):
                continue
        filtered.append(f)

    return _sort_files(filtered)


def get_file_link(token, ident):
    xml = _post('file_link', {
        'ident':         ident,
        'download_type': 'video_stream',
        'force_https':   1,
    }, token=token)
    if not xml or _x(xml, 'status') != 'OK':
        xbmc.log('WS file_link [%s] failed: %s' % (ident, _x(xml, 'message')), xbmc.LOGERROR)
        return None
    return _x(xml, 'link') or None
