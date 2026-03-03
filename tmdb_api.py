# -*- coding: utf-8 -*-
"""
Stream Cinema Caolina v2.1.0
Entry point — WSC styl (identický s yawsp/wsc main.py)
"""
import sys
import os

# Přidej adresář doplňku do sys.path aby importy fungovaly
addon_dir = os.path.dirname(os.path.abspath(__file__))
if addon_dir not in sys.path:
    sys.path.insert(0, addon_dir)

import addon as scc_addon

if __name__ == '__main__':
    from urllib.parse import parse_qsl
    params = dict(parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 and sys.argv[2] else {}
    scc_addon.router(params)
