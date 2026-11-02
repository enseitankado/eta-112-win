# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Onboard ethernet MAC adresi: oku · doğrula · değiştir.

OKU/DOĞRULA: Windows'ta sürücüsüz, güvenle çalışır (GetAdaptersInfo + saf kural
denetimi). DEĞİŞTİR: MAC, Realtek NIC'in eFuse'unda (OTP) tutulur; kalıcı/OS-bağımsız
değişiklik yalnız Realtek'in Windows PG aracıyla (imzalı sürücü) yapılabilir. Linux
portundaki rtnicpg+pgdrv derleme yolu Windows'ta geçerli değildir; bu port eFuse
yazmayı otomatikleştirmez, gerekli aracı ve adımı bildirir.
"""

import ctypes
from ctypes import wintypes

from . import ui
from .ui import (R, G, Y, Cy, D, OK, WARN, ERR, emit)
from .model import dmi
from .profiles import match_profile

_JSON = lambda: ui.JSON


# ===================== saf kural mantığı (eta-112 ile birebir) =====================
def _norm_mac(s):
    if not s:
        return None
    h = "".join(c for c in s if c in "0123456789abcdefABCDEF")
    if len(h) != 12:
        return None
    return ":".join(h[i:i + 2] for i in range(0, 12, 2)).upper()


def _mac_oui(mac):
    return mac[:8] if mac else None


def validate_mac(mac_in, prof):
    ouis = (prof or {}).get("mac_ouis")
    m = _norm_mac(mac_in)
    if not m:
        return (False, None, None, None, "biçim geçersiz (12 onaltılık hane gerekir)")
    first = int(m[:2], 16)
    if m == "00:00:00:00:00:00":
        return (False, m, None, None, "hepsi-sıfır MAC geçersiz")
    if m == "FF:FF:FF:FF:FF:FF":
        return (False, m, _mac_oui(m), None, "broadcast MAC geçersiz")
    if first & 1:
        return (False, m, _mac_oui(m), None, "çok-noktalı (multicast) adres — NIC MAC'i olamaz")
    oui = _mac_oui(m)
    if ouis is None:
        return (False, m, oui, None, "bu model için Faz OUI doğrulaması tanımlı değil")
    if first & 2:
        return (False, m, oui, None, "yerel-yönetimli (rastgele) adres — Faz cihazları global OUI kullanır")
    if oui not in ouis:
        return (False, m, oui, None, "OUI %s Faz'a ait değil (izinli: %s)" % (oui, ", ".join(ouis)))
    return (True, m, oui, ouis[oui], None)


# ===================== Windows ethernet arayüzleri =====================
MAX_ADAPTER_NAME_LENGTH = 256
MAX_ADAPTER_ADDRESS_LENGTH = 8
MAX_ADAPTER_DESCRIPTION_LENGTH = 128
MIB_IF_TYPE_ETHERNET = 6


class _IP_ADDR_STRING(ctypes.Structure):
    pass


_IP_ADDR_STRING._fields_ = [
    ("Next", ctypes.POINTER(_IP_ADDR_STRING)),
    ("IpAddress", ctypes.c_char * 16),
    ("IpMask", ctypes.c_char * 16),
    ("Context", wintypes.DWORD),
]


class _IP_ADAPTER_INFO(ctypes.Structure):
    pass


_IP_ADAPTER_INFO._fields_ = [
    ("Next", ctypes.POINTER(_IP_ADAPTER_INFO)),
    ("ComboIndex", wintypes.DWORD),
    ("AdapterName", ctypes.c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
    ("Description", ctypes.c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
    ("AddressLength", wintypes.UINT),
    ("Address", ctypes.c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
    ("Index", wintypes.DWORD),
    ("Type", wintypes.UINT),
    ("DhcpEnabled", wintypes.UINT),
    ("CurrentIpAddress", ctypes.POINTER(_IP_ADDR_STRING)),
    ("IpAddressList", _IP_ADDR_STRING),
    ("GatewayList", _IP_ADDR_STRING),
    ("DhcpServer", _IP_ADDR_STRING),
    ("HaveWins", wintypes.BOOL),
    ("PrimaryWinsServer", _IP_ADDR_STRING),
    ("SecondaryWinsServer", _IP_ADDR_STRING),
    ("LeaseObtained", ctypes.c_long),
    ("LeaseExpires", ctypes.c_long),
]


def _eth_ifaces():
    """[(ad/açıklama, MAC, sürücü-açıklaması)] — yalnız kablolu ethernet."""
    try:
        iphlp = ctypes.windll.iphlpapi
    except Exception:
        return []
    size = wintypes.ULONG(0)
    iphlp.GetAdaptersInfo(None, ctypes.byref(size))
    if size.value == 0:
        return []
    buf = ctypes.create_string_buffer(size.value)
    if iphlp.GetAdaptersInfo(buf, ctypes.byref(size)) != 0:
        return []
    out = []
    p = ctypes.cast(buf, ctypes.POINTER(_IP_ADAPTER_INFO))
    while p:
        a = p.contents
        if a.Type == MIB_IF_TYPE_ETHERNET and a.AddressLength == 6:
            mac = ":".join("%02X" % a.Address[i] for i in range(6))
            desc = a.Description.decode("latin-1", "replace").strip()
            out.append((a.AdapterName.decode("latin-1", "replace"), mac, desc))
        p = a.Next if a.Next else None
    return out


def _mac_profile():
    d = dmi()
    return match_profile(d), d


# ===================== komutlar =====================
def cmd_mac_read(a):
    prof, d = _mac_profile()
    ouis = (prof or {}).get("mac_ouis")
    ifs = _eth_ifaces()
    if _JSON():
        items = [{"iface": i, "mac": m, "driver": v, "oui": _mac_oui(m),
                  "vendor": (ouis or {}).get(_mac_oui(m)),
                  "faz_uyumlu": bool(ouis and _mac_oui(m) in ouis)} for i, m, v in ifs]
        return emit({"ok": True, "supported": bool(prof),
                     "model": (prof or {}).get("model_name"), "board": d.get("board"),
                     "interfaces": items, "allowed_ouis": ouis})
    print(f"  Model: {G(prof['model_name']) if prof else Y('(tanınmadı)')}  "
          f"{D('Kart ' + str(d.get('board', '?')))}")
    if not ifs:
        print(R("  Kablolu ethernet arayüzü bulunamadı."))
        return 1
    print("\n  Ethernet MAC adresleri")
    for name, mac, drv in ifs:
        oui = _mac_oui(mac)
        if ouis and oui in ouis:
            tag = f"{OK} {G('Faz OUI')} {D('(' + ouis[oui] + ')')}"
        elif ouis:
            tag = f"{WARN} {Y('Faz OUI değil')}"
        else:
            tag = D("(model profili yok)")
        print(f"  {Cy(mac)}  {D('[' + drv + ']')}  {tag}")
    if ouis:
        print(D("\n  İzinli Faz OUI: ") + ", ".join("%s (%s)" % (o, v) for o, v in ouis.items()))
    else:
        print(D("\n  (Bu model için OUI beyaz listesi tanımlı değil.)"))
    return 0


def cmd_mac_check(a):
    prof, _d = _mac_profile()
    ok, m, oui, vendor, reason = validate_mac(a.mac, prof)
    if _JSON():
        return emit({"ok": ok, "mac": m, "oui": oui, "vendor": vendor, "reason": reason},
                    0 if ok else 1)
    if ok:
        print(f"  {OK} {G('Geçerli Faz MAC')}: {Cy(m)}  {D('OUI ' + oui + ' — ' + vendor)}")
        print(D("     Doğrulama yalnız adresin kendisini sınar; donanıma hiçbir şey yazılmadı."))
        return 0
    print(f"  {ERR} {R('Geçersiz MAC')}: {a.mac}")
    if m:
        print(D("     normalize: %s%s" % (m, "  OUI " + oui if oui else "")))
    print(f"     {Y('neden: ' + reason)}")
    return 1


_PGTOOL_NOTE = (
    "Windows'ta onboard MAC, Realtek NIC'in eFuse'unda (OTP) tutulur ve yalnız "
    "Realtek'in Windows PG aracıyla (ör. PG8168 / RtNicpg, imzalı sürücü) yazılabilir. "
    "Linux portundaki rtnicpg+pgdrv derleme yolu Windows'ta geçerli değildir. Bu "
    "port eFuse yazmayı otomatikleştirmez (brick/kalıcı tüketim riski). Önerilen adım: "
    "doğru MAC'i 'mac check <MAC>' ile doğrulayın, ardından Realtek PG aracıyla yazın. "
    "eFuse = tek-yönlü kalıcı (OTP): yazılan geri alınamaz, boş alan tükenince MAC bir "
    "daha değiştirilemez."
)


def cmd_mac_set(a):
    prof, _d = _mac_profile()
    ok, m, oui, vendor, reason = validate_mac(a.mac, prof)
    if not ok:
        if _JSON():
            return emit({"ok": False, "error": reason, "mac": m}, 1)
        print(f"  {ERR} {R('Geçersiz MAC')}: {Y(reason)}")
        return 1
    if _JSON():
        return emit({"ok": False, "supported": False, "mac": m,
                     "error": "windows_efuse_pgtool_required", "note": _PGTOOL_NOTE}, 2)
    print(f"  {OK} {G('MAC geçerli')}: {Cy(m)}  {D('(' + (vendor or oui) + ')')}")
    print()
    print(f"  {WARN} {Y('Windows eFuse yazma bu portta otomatik değildir.')}")
    for line in _wrap(_PGTOOL_NOTE):
        print(D("     " + line))
    return 2


def _wrap(text, width=72):
    import textwrap
    return textwrap.wrap(text, width)
