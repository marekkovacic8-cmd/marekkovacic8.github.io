# -*- coding: utf-8 -*-
#########################################################
# md5crypt.py — FreeBSD MD5-crypt ($1$)
#
# Vrací STRING "$1$salt$hash" — identické s SCC unix_md5_crypt.
# Webshare login: SHA1( md5crypt(pw, salt).encode('utf-8') ).hexdigest()
#########################################################

import hashlib

MAGIC = '$1$'
ITOA64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def to64(v, n):
    ret = ''
    while n - 1 >= 0:
        n -= 1
        ret += ITOA64[v & 0x3f]
        v >>= 6
    return ret


def md5crypt(pw, salt, magic=None):
    """
    Unix MD5-Crypt ($1$) — vraci STRING "$1$salt$hash"
    Identicky vystup jako SCC unix_md5_crypt.
    Webshare login: SHA1( md5crypt(pw, salt).encode('utf-8') ).hexdigest()
    """
    if magic is None:
        magic = MAGIC

    # Normalizuj na str
    if isinstance(pw, bytes):
        pw = pw.decode('utf-8')
    if isinstance(salt, bytes):
        salt = salt.decode('utf-8')
    if isinstance(magic, bytes):
        magic = magic.decode('utf-8')

    # Odstran magic prefix ze saltu
    if salt.startswith(magic):
        salt = salt[len(magic):]

    # Salt max 8 znaku, orizni na $
    if '$' in salt:
        salt = salt[:salt.index('$')]
    salt = salt[:8]

    # Pracujeme s bytes pro MD5
    pw_b    = pw.encode('utf-8')
    salt_b  = salt.encode('utf-8')
    magic_b = magic.encode('utf-8')

    ctx = pw_b + magic_b + salt_b
    final = hashlib.md5(pw_b + salt_b + pw_b).digest()

    for pl in range(len(pw_b), 0, -16):
        if pl > 16:
            ctx += final[:16]
        else:
            ctx += final[:pl]

    i = len(pw_b)
    while i:
        if i & 1:
            ctx += b'\x00'
        else:
            ctx += pw_b[0:1]
        i >>= 1

    final = hashlib.md5(ctx).digest()

    for i in range(1000):
        ctx1 = b''
        if i & 1:
            ctx1 += pw_b
        else:
            ctx1 += final[:16]
        if i % 3:
            ctx1 += salt_b
        if i % 7:
            ctx1 += pw_b
        if i & 1:
            ctx1 += final[:16]
        else:
            ctx1 += pw_b
        final = hashlib.md5(ctx1).digest()

    # Final xform
    passwd = ''
    passwd += to64((final[0] << 16) | (final[6] << 8)  | final[12], 4)
    passwd += to64((final[1] << 16) | (final[7] << 8)  | final[13], 4)
    passwd += to64((final[2] << 16) | (final[8] << 8)  | final[14], 4)
    passwd += to64((final[3] << 16) | (final[9] << 8)  | final[15], 4)
    passwd += to64((final[4] << 16) | (final[10] << 8) | final[5],  4)
    passwd += to64(final[11], 2)

    # Vrati STRING jako SCC unix_md5_crypt
    return magic + salt + '$' + passwd
