<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.streamcinema.caolina"
       name="Stream Cinema Caolina"
       version="2.1.5"
       provider-name="Caolina">
  <requires>
    <import addon="xbmc.python" version="3.0.0"/>
  </requires>
  <extension point="xbmc.python.pluginsource" library="main.py">
    <provides>video</provides>
  </extension>
  <extension point="xbmc.addon.metadata">
    <summary lang="cs_CZ">Filmy a seriály z Webshare.cz s CSFD/TMDB</summary>
    <summary lang="en_GB">Movies and TV shows from Webshare.cz with CSFD/TMDB</summary>
    <description lang="cs_CZ">Stream Cinema Caolina - Streamování filmů a seriálů z Webshare.cz. CSFD prioritní vyhledávání, TMDB fallback. Funguje na Kodi 18, 19, 20, 21.</description>
    <description lang="en_GB">Stream Cinema Caolina - Stream movies and TV shows from Webshare.cz. CSFD priority search, TMDB fallback. Works on Kodi 18, 19, 20, 21.</description>
    <platform>all</platform>
    <license>GPL-3.0</license>
    <assets>
      <icon>icon.png</icon>
      <fanart>fanart.jpg</fanart>
    </assets>
    <news>
v2.1.5 - Prísnejsi vyhledavani: titul-part matching, fix Red Dwarf/Avatar
v2.1.4 - QR dobrovolny prispevek
v2.1.3 - VIP badge s poctem dni, opraveno menu pred spustenim
v2.1.2 - Opraveno vyhledávání seriálů: 4 vlny (EN+CZ+kw_EN+kw_CZ), správné řazení epizod
v2.1.1 - Menu identické s Enigma2 provider.py
v2.1.0 - WSC architektura, opravený login, CSFD+TMDB+OMDB databáze
    </news>
  </extension>
</addon>
