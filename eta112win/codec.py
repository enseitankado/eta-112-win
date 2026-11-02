# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Platform-bağımsız çözümleme mantığı (eta-112'den BİREBİR taşındı).

BIOS parola blob'unun XOR-keystream ile çözülmesi/kodlanması, Türkçe-Q klavye
normalizasyonu ve AMI Aptio NVAR/Setup değişkenlerinin flash imajından ayıklanması.
Bu kod yalnız bayt işler; işletim sisteminden bağımsızdır, Linux ile birebir aynıdır.
"""

import struct


# ===================== KARAKTER / TÜRKÇE-Q =====================
# BIOS parolayı US scancode'una göre saklar; bu cihazlarda Türkçe-Q klavye
# kullanıldığı için GÖRÜNTÜ normalleştirilir (US -> Türkçe-Q aynı fiziksel tuş).
TURKCE_Q = {"'": "İ", '"': "İ", ";": "Ş", ":": "Ş", "[": "Ğ", "{": "Ğ", "]": "Ü", "}": "Ü",
            ",": "Ö", "<": "Ö", ".": "Ç", ">": "Ç", "/": ".", "?": ":", "\\": ",", "|": ";"}
INV_TURKCE_Q = {"i": "'", "İ": "'", "ı": "i", "ş": ";", "Ş": ";", "ğ": "[", "Ğ": "[",
                "ü": "]", "Ü": "]", "ö": ",", "Ö": ",", "ç": ".", "Ç": "."}


def trq(s):
    return "".join(TURKCE_Q.get(c, c) for c in s) if s else s


def to_bios(pw, maxlen):
    """Kullanıcı girişini BIOS'un saklayacağı biçime çevirir:
    Türkçe-Q -> US fiziksel tuş, ardından BÜYÜK HARF, sonra uzunluk sınırı."""
    s = "".join(INV_TURKCE_Q.get(c, c) for c in pw).upper()
    return s[:maxlen]


# ===================== şifre çözme / kodlama =====================
def decode(slot, ks):
    if slot == b"\x00" * len(ks):
        return None
    return bytes(a ^ b for a, b in zip(slot, ks)).decode("utf-16-le", "replace").rstrip("\x00")


def obf(pw, ks):
    b = pw.encode("utf-16-le")
    b = (b + b"\x00" * len(ks))[:len(ks)]
    return bytes(a ^ c for a, c in zip(b, ks))


def is_clean(s):
    return s is not None and len(s) > 0 and all(32 <= ord(c) < 127 for c in s)


# ===================== NVAR / AMI Aptio değişken tarama =====================
def nvar_scan(data, store_len=61):
    out = []
    n = len(data)
    NV = b"NVAR"
    i = data.find(NV)
    while i != -1 and i < n - 10:
        size = struct.unpack("<H", data[i + 4:i + 6])[0]
        if 8 < size < 0x800 and i + size <= n:
            nxt = data[i + 6] | (data[i + 7] << 8) | (data[i + 8] << 16)
            flags = data[i + 9]
            name = b""
            if flags & 0x02:
                end = data.find(b"\x00", i + 11)
                doff = (end + 1) - i if end != -1 else 10
                name = data[i + 11:end] if end != -1 else b""
            else:
                doff = 10
            if size - doff == store_len:
                out.append({"off": i, "data_off": i + doff, "flags": flags, "next": nxt,
                            "name": name, "blob": data[i + doff:i + doff + store_len]})
            i = data.find(NV, i + size)
        else:
            i = data.find(NV, i + 1)
    return out


def nvar_setup_payload(data, active_end, setup_len=(330, 345)):
    lo, hi = setup_len
    best = None
    n = len(data)
    NV = b"NVAR"
    i = data.find(NV)
    while i != -1 and i < n - 10:
        size = struct.unpack("<H", data[i + 4:i + 6])[0]
        if 8 < size < 0x800 and i + size <= n:
            flags = data[i + 9]
            if flags & 0x02:
                end = data.find(b"\x00", i + 11)
                doff = (end + 1) - i if end != -1 else 10
            else:
                doff = 10
            blob = data[i + doff:i + size]
            if lo <= len(blob) <= hi and i < active_end:
                best = blob
            i = data.find(NV, i + size)
        else:
            i = data.find(NV, i + 1)
    return best


def _bank_tail(es):
    """Bir bankanın zincir sonu (next=FFFFFF, en yüksek ofset)."""
    if not es:
        return None
    ts = [e for e in es if e["next"] == 0xFFFFFF]
    return max(ts, key=lambda e: e["off"]) if ts else max(es, key=lambda e: e["off"])


def _chain_named(es):
    """Zinciri başlatan isimli AMITSESetup girişi (reclaim anındaki değer)."""
    nm = [e for e in es if e["name"] == b"AMITSESetup" and e["next"] != 0xFFFFFF]
    return min(nm, key=lambda e: e["off"]) if nm else None


def resolve_current(entries, banks):
    """Çift-banka NVRAM'de GERÇEK güncel parolayı bulur. Aktif banka = diğerinin
    zincir-sonundan devam eden (daha yeni reclaim edilmiş) banka."""
    if not banks or len(banks) < 2:
        t = _bank_tail(entries)
        return t["blob"] if t else None
    (a0, a1), (b0, b1) = banks[0], banks[1]
    A = [e for e in entries if a0 <= e["off"] < a1]
    B = [e for e in entries if b0 <= e["off"] < b1]
    tA = _bank_tail(A)
    tB = _bank_tail(B)
    if tA is None:
        return tB["blob"] if tB else None
    if tB is None:
        return tA["blob"]
    nA = _chain_named(A)
    nB = _chain_named(B)
    if nB and nB["blob"][:60] == tA["blob"][:60]:
        return tB["blob"]
    if nA and nA["blob"][:60] == tB["blob"][:60]:
        return tA["blob"]
    return (tB if tB["off"] > tA["off"] else tA)["blob"]


def pw_filter(entries, prof):
    """Parola store'unu adıyla ayıkla (store_name verilmişse). Bazı kartlarda
    store_len başka NVAR'larla çakışır; yanlış blob okuma/yazmayı önler."""
    nm = prof.get("store_name")
    return [e for e in entries if e["name"] == nm] if nm else entries


def scan(data, prof):
    return (nvar_scan(data, prof.get("store_len", 61)),
            nvar_setup_payload(data, prof["active_store_end"], prof.get("setup_len", (330, 345))))
