# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Donanımsız uçtan uca doğrulama: BIOS parolası oku · yaz · temizle mantığı.

Sentetik bir AMI Aptio NVAR flash imajı üretir, bilinen bir parolayı keystream ile
gömer ve aracın çözümleme/düzenleme hattını (codec + bios._edit_image/_dryrun_write)
baştan sona sınar. CHIPSEC, yönetici hakkı veya gerçek donanım GEREKMEZ — bu yüzden
CI'da ve herhangi bir makinede çalışır.

Çalıştırma:
    python -m pytest tests/ -q
    python tests/test_bios_roundtrip.py      # pytest yoksa düz çalıştırır
"""

import os
import sys
import struct
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eta112win import codec, bios              # noqa: E402
from eta112win.profiles import PROFILES        # noqa: E402

PROF = PROFILES[("14MB57", "4.6.5")]           # Faz 2 Vestel Intel (Gri)


# ---- sentetik imaj kurucu ----
def _nvar(payload, nxt=0xFFFFFF, name=None):
    """nvar_scan'in tanıyacağı tek bir NVAR kaydı üretir.
    name=None -> isimsiz kayıt (flags&0x02 yok), doff=10 (14MB57 böyle)."""
    flags = 0x00
    extra = b""
    if name is not None:
        flags |= 0x02
        # nvar_scan ismi i+11'den okur; i+10'da bir bayt vardır
        extra = b"\x00" + name + b"\x00"
    doff = 10 + len(extra)
    size = doff + len(payload)
    assert 8 < size < 0x800
    nxt_b = bytes([nxt & 0xFF, (nxt >> 8) & 0xFF, (nxt >> 16) & 0xFF])
    hdr = b"NVAR" + struct.pack("<H", size) + nxt_b + bytes([flags])
    return hdr + extra + payload


def _store_blob(user=None, super_=None):
    """81 baytlık parola store'u: [0:40]=kullanıcı, [40:80]=yönetici, [80]=pad."""
    ks = PROF["keystream"]
    sl = PROF["slot_len"]
    u = codec.obf(codec.to_bios(user, PROF["pw_max"]), ks) if user else b"\x00" * sl
    s = codec.obf(codec.to_bios(super_, PROF["pw_max"]), ks) if super_ else b"\x00" * sl
    blob = bytearray(PROF["store_len"])
    blob[PROF["slot_user"]:PROF["slot_user"] + sl] = u
    blob[PROF["slot_super"]:PROF["slot_super"] + sl] = s
    return bytes(blob)


def _image(user=None, super_=None):
    """Store kaydını A bankasının başına koyan tam bir BIOS-bölgesi imajı."""
    img = bytearray(b"\xff" * PROF["active_store_end"])
    rec = _nvar(_store_blob(user, super_))
    at = PROF["banks"][0][0]                    # 0x400000
    img[at:at + len(rec)] = rec
    return bytes(img)


# ---- okuma yardımcıları ----
def _read_passwords(data):
    ents = codec.pw_filter(codec.nvar_scan(data, PROF["store_len"]), PROF)
    cur = codec.resolve_current(ents, PROF["banks"])
    ks, su, sp, sl = PROF["keystream"], PROF["slot_user"], PROF["slot_super"], PROF["slot_len"]
    du = codec.decode(cur[su:su + sl], ks) if cur else None
    ds = codec.decode(cur[sp:sp + sl], ks) if cur else None
    return (codec.trq(du) if du else None, codec.trq(ds) if ds else None)


# ---- testler ----
def test_read_known_password():
    data = _image(super_="ADMIN1")
    user, sup = _read_passwords(data)
    assert sup == "ADMIN1", sup
    assert user is None, user


def test_read_empty():
    data = _image()
    assert _read_passwords(data) == (None, None)


def test_calibrate_recovers_keystream():
    """Bilinen parolayla slot'tan türetilen keystream profilinkiyle birebir olmalı."""
    data = _image(super_="ADMIN1")
    ents = codec.pw_filter(codec.nvar_scan(data, PROF["store_len"]), PROF)
    cur = codec.resolve_current(ents, PROF["banks"])
    sl, sp = PROF["slot_len"], PROF["slot_super"]
    slot = cur[sp:sp + sl]
    b = codec.to_bios("ADMIN1", PROF["pw_max"]).encode("utf-16-le")
    b = (b + b"\x00" * sl)[:sl]
    derived = bytes(x ^ y for x, y in zip(slot, b))
    assert derived == PROF["keystream"], derived.hex()


def test_dryrun_set_then_reread():
    """set (dry-run): kullanıcı ekle + yöneticiyi değiştir -> dosyaya yaz -> geri oku."""
    data = _image(super_="OLDADM")
    ks = PROF["keystream"]
    edits = [(PROF["slot_super"], codec.obf(codec.to_bios("NEWADM", PROF["pw_max"]), ks)),
             (PROF["slot_user"], codec.obf(codec.to_bios("USER22", PROF["pw_max"]), ks))]
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.bin")
        out = os.path.join(d, "out.bin")
        with open(src, "wb") as f:
            f.write(data)
        res = bios._dryrun_write(PROF, edits, None, src, out)
        assert res["ok"] and res["changed"] and res["verified"], res
        with open(out, "rb") as f:
            new = f.read()
    assert len(new) == len(data)
    user, sup = _read_passwords(new)
    assert (user, sup) == ("USER22", "NEWADM"), (user, sup)


def test_dryrun_clear_all():
    data = _image(user="USER22", super_="NEWADM")
    z = b"\x00" * PROF["slot_len"]
    edits = [(PROF["slot_user"], z), (PROF["slot_super"], z)]
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.bin")
        out = os.path.join(d, "out.bin")
        with open(src, "wb") as f:
            f.write(data)
        res = bios._dryrun_write(PROF, edits, None, src, out)
        assert res["ok"] and res["changed"] and res["verified"], res
        with open(out, "rb") as f:
            new = f.read()
    assert _read_passwords(new) == (None, None)


def test_write_confined_to_bank():
    """Yazılan tek fark parola bankası aralığında, store kaydının içinde olmalı."""
    data = _image(super_="OLDADM")
    ks = PROF["keystream"]
    edits = [(PROF["slot_super"], codec.obf(codec.to_bios("NEWADM", PROF["pw_max"]), ks))]
    new, changes = bios._edit_image(data, PROF, edits)
    assert changes, "değişiklik bekleniyordu"
    (lo, hi) = PROF["banks"][0]
    for off, _old, _val in changes:
        assert lo <= off < hi, "banka dışına yazma: 0x%X" % off
    # bankalar dışında hiçbir bayt değişmemeli
    diff = [i for i in range(len(data)) if data[i] != new[i]]
    assert all(any(b0 <= i < b1 for (b0, b1) in PROF["banks"]) for i in diff)


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("  ok   %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("  FAIL %s: %s" % (t.__name__, e))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("  ERR  %s: %r" % (t.__name__, e))
    print("\n%d/%d geçti" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
