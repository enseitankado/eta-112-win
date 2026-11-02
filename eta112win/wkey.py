# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""BIOS'taki Windows ürün anahtarı (ACPI MSDM) oku / değiştir.

OKUMA: GetSystemFirmwareTable('ACPI','MSDM') ile sürücüsüz, güvenle çalışır.
DEĞİŞTİRME: flash'taki MSDM tablosunu düzenleyip ACPI checksum'ı günceller ve
CHIPSEC ile geri yazar — brick riski taşır, Windows portunda donanım testi YAPILMADI.
"""

import re
import struct

from . import ui, flash
from .ui import (R, G, Y, Cy, D, OK, WARN, ERR, emit)
from .firmware import read_acpi_table, has_acpi_table
from .bios import need_profile

_JSON = lambda: ui.JSON
_WKEY_RE = r"[A-Z0-9]{5}(?:-[A-Z0-9]{5}){4}"


def validate_wkey(s):
    k = (s or "").strip().upper()
    if not re.fullmatch(_WKEY_RE, k):
        return False, None, "biçim XXXXX-XXXXX-XXXXX-XXXXX-XXXXX olmalı (5×5, A-Z 0-9)"
    return True, k, None


def _msdm_find_key(tbl):
    m = re.search(_WKEY_RE.encode(), tbl or b"")
    return (m.group().decode(), m.start()) if m else (None, None)


def _acpi_checksum_fix(tbl):
    b = bytearray(tbl)
    b[9] = 0
    b[9] = (256 - (sum(b) % 256)) % 256
    return bytes(b)


def cmd_wkey_read(a):
    if not ui.is_admin():
        return emit({"ok": False, "error": "yönetici gerekli"}, 1) if _JSON() else \
            (print(R("  MSDM okuma için yönetici (Administrator) gerekli.")) or 1)
    raw = read_acpi_table("MSDM")
    slic = has_acpi_table("SLIC")
    if raw is None:
        if _JSON():
            return emit({"ok": True, "present": False, "slic": slic, "key": None})
        print(Y("  MSDM tablosu yok — bu makinede okunabilir Windows ürün anahtarı saklanmıyor."))
        if slic:
            print(D("  (SLIC var: Windows 7/Vista OEM aktivasyonu — okunabilir anahtar içermez.)"))
        return 1
    key, _off = _msdm_find_key(raw)
    if _JSON():
        return emit({"ok": bool(key), "present": True, "key": key})
    if key:
        print(f"  {OK} {G('Windows ürün anahtarı (MSDM)')}: {Cy(key)}")
    else:
        print(Y("  MSDM tablosu var ama anahtar çözülemedi."))
        return 1
    return 0


def cmd_wkey_set(a):
    if not ui.is_admin():
        return emit({"ok": False, "error": "yönetici gerekli"}, 1) if _JSON() else \
            (print(R("  Bunun için yönetici (Administrator) gerekli.")) or 1)
    prof, _d = need_profile()
    if not prof:
        return emit({"ok": False, "error": "desteklenmeyen model"}, 1) if _JSON() else \
            (print(R("  Desteklenmeyen model (flash erişimi için profil gerekli).")) or 1)
    ok, newkey, reason = validate_wkey(a.key)
    if not ok:
        if _JSON():
            return emit({"ok": False, "error": reason}, 1)
        print(f"  {ERR} {R('Geçersiz anahtar')}: {Y(reason)}")
        return 1
    if not flash.available():
        return emit({"ok": False, "error": "CHIPSEC yok"}, 1) if _JSON() else \
            (print(R("  CHIPSEC bulunamadı — MSDM yazma için gerekli.")) or 1)
    sess = flash.FlashSession(prof)
    try:
        try:
            data = sess.read_region()
        except flash.FlashError as e:
            return emit({"ok": False, "error": str(e)}, 1) if _JSON() else (print(R("  " + str(e))) or 1)
        i = data.find(b"MSDM")
        if i == -1:
            msg = "MSDM flash'ta bulunamadı (bu cihazda Windows anahtarı yok ya da sıkıştırılmış)"
            return emit({"ok": False, "error": "no_msdm"}, 1) if _JSON() else (print(Y("  " + msg + ".")) or 1)
        length = struct.unpack("<I", bytes(data[i + 4:i + 8]))[0]
        if not (36 < length < 0x2000) or i + length > len(data):
            return emit({"ok": False, "error": "MSDM uzunluğu geçersiz"}, 1) if _JSON() else \
                (print(R("  Flash'taki MSDM tablosu geçersiz.")) or 1)
        tbl = bytes(data[i:i + length])
        fk, koff = _msdm_find_key(tbl)
        if not fk or len(fk) != len(newkey):
            return emit({"ok": False, "error": "flash MSDM'de anahtar bulunamadı"}, 1) if _JSON() else \
                (print(R("  Flash MSDM'de anahtar bulunamadı.")) or 1)
        if fk == newkey:
            return emit({"ok": True, "changed": False, "key": newkey, "note": "zaten bu anahtar"}) if _JSON() else \
                (print(Y("  Anahtar zaten bu değerde.")) or 0)
        nt = bytearray(tbl)
        nt[koff:koff + len(newkey)] = newkey.encode("ascii")
        nt = _acpi_checksum_fix(bytes(nt))
        new = bytearray(data)
        new[i:i + length] = nt
        if not _JSON() and not getattr(a, "yes", False):
            print(f"\n  Mevcut anahtar : {Cy(fk)}")
            print(f"  Yeni anahtar   : {G(newkey)}")
            print(f"  {WARN} {Y('BIOS flash MSDM tablosu değiştirilir (CHIPSEC). Brick riski; Windows portunda donanım testi YAPILMADI.')}")
            if not ui.confirm_evet("Onaylıyorsanız EVET yazın: "):
                print(Y("  İptal edildi."))
                return 0
            print(D("  Yazılıyor..."), flush=True)
        wok, msg = sess.write_raw_region(bytes(new))
        verified = wok and ("doğrulan" in msg)
        if verified:
            # içerik düzeyinde ikinci doğrulama
            try:
                rb = sess.read_region()
                j = rb.find(b"MSDM")
                if j != -1:
                    l2 = struct.unpack("<I", bytes(rb[j + 4:j + 8]))[0]
                    t2 = bytes(rb[j:j + l2])
                    k2, _ = _msdm_find_key(t2)
                    verified = (k2 == newkey) and (sum(t2) % 256 == 0)
                else:
                    verified = False
            except flash.FlashError:
                verified = False
    finally:
        sess.close()
    if _JSON():
        return emit({"ok": bool(wok), "changed": True, "verified": verified, "key": newkey, "old": fk},
                    0 if (wok and verified) else 1)
    if not wok:
        print(f"  {ERR} {R('Yazma başarısız (CHIPSEC)')}: {msg}")
        return 1
    if verified:
        print(f"  {OK} {G('MSDM yazıldı ve DOĞRULANDI')} — anahtar: {Cy(newkey)}")
    else:
        print(f"  {WARN} {Y('Yazıldı ama geri-oku doğrulaması tutmadı.')}")
    print(f"  {Y('Yeniden başlatın')} — Windows yeni anahtarı MSDM'den okur. 'wkey read' ile doğrulayın.")
    return 0
