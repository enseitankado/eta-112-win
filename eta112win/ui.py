# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Konsol arabirimi: renkler, giriş alma, onay, yönetici kontrolü ve
Windows ok-tuşlu menü (msvcrt). JSON (makine) kipi renkleri ve etkileşimi kapatır.
"""

import sys
import ctypes

# Çıktıyı UTF-8'e sabitle: ✓/emoji/Türkçe karakterler, çıktı dosyaya/pipe'a
# yönlendirildiğinde (Windows'ta cp1254) 'UnicodeEncodeError' ile çökmesin.
for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---- JSON (makine) kipi: cli tarafından ayarlanır ----
JSON = False


def set_json(v):
    global JSON
    JSON = bool(v)


def emit(obj, code=0):
    """JSON (makine) kipinde makine-okur çıktı yazar."""
    import json
    print(json.dumps(obj, ensure_ascii=False))
    return code


# ---- renk ----
class C:
    R = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
    CY = "\033[36m"; GR = "\033[32m"; RD = "\033[31m"; YL = "\033[33m"


def _enable_vt():
    """Windows konsolunda ANSI/VT işlemeyi aç (Win10+). Başarısızsa renkleri kapat."""
    try:
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


if not sys.stdout.isatty() or (sys.platform == "win32" and not _enable_vt()):
    for _a in ("R", "B", "DIM", "CY", "GR", "RD", "YL"):
        setattr(C, _a, "")


def _c(code, s):
    return f"\033[{code}m{s}\033[0m" if getattr(C, "R") else s


def B(s):  return _c("1", s)
def R(s):  return _c("1;31", s)
def G(s):  return _c("1;32", s)
def Y(s):  return _c("1;33", s)
def Cy(s): return _c("1;36", s)
def D(s):  return _c("2", s)


OK = G("✓")
WARN = Y("!")
ERR = R("✗")


def hr():
    print(C.DIM + "─" * 60 + C.R)


def title(t):
    print()
    print(C.CY + C.B + "  " + t + C.R)
    hr()


def ok(m):   print(f"  {OK} {m}")
def warn(m): print(f"  {WARN} {m}")
def err(m):  print(f"  {ERR} {m}", file=sys.stderr)


def die(m, code=1):
    err(m)
    sys.exit(code)


def ask(prompt=""):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError("girdi sonu")
    return line.rstrip("\n")


def ask_pw(prompt):
    import getpass
    try:
        return getpass.getpass(prompt)
    except Exception:
        return ask(prompt)


def confirm_evet(prompt="Onaylıyorsanız EVET yazın: "):
    """Yüksek riskli işlemler için açık 'EVET' onayı (tr)."""
    try:
        return ask("  " + prompt).strip() == "EVET"
    except EOFError:
        return False


def confirm_eh(prompt, default_no=True):
    """e/h onayı. Boş yanıt = varsayılan (default_no ise hayır)."""
    try:
        a = ask("  " + prompt + (" [e/H]: " if default_no else " [E/h]: ")).strip().lower()
    except EOFError:
        return False
    if not a:
        return not default_no
    return a in ("e", "evet", "y", "yes")


# ---- yönetici (admin) kontrolü ----
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def require_admin():
    """Yönetici değilse açıklayıcı mesaj basıp False döner."""
    if is_admin():
        return True
    if not JSON:
        err("Bu işlem için YÖNETİCİ (Administrator) olarak çalıştırmanız gerekir.")
        print(D("     PowerShell/CMD'yi 'Yönetici olarak çalıştır' ile açıp tekrar deneyin."))
    return False


# ---- ok-tuşlu menü (yalnız etkileşimli tty) ----
_MENU_IPUCU = "↑/↓ gez · Enter seç · 1-9 doğrudan · Esc geri"


def _interactive():
    return sys.platform == "win32" and sys.stdin.isatty() and sys.stdout.isatty()


def _read_key():
    """Windows: tek tuş oku. Döner: 'up'/'down'/'enter'/'esc'/digit/char/None."""
    import msvcrt
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):          # özel tuş öneki (ok tuşları)
        ch2 = msvcrt.getwch()
        return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(ch2)
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x1b":
        return "esc"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def _draw(baslik, ogeler, secili, yol, esc_uyari=False):
    print("\033[2J\033[H", end="")  # ekranı temizle
    bc = " > ".join(yol) if yol else baslik
    print()
    print("  " + B(Cy(bc)))
    hr()
    for i, (etiket, aciklama, *_r) in enumerate(ogeler):
        isaret = "▸" if i == secili else " "
        no = str(i + 1) if i < 9 else " "
        satir = f"  {Cy(isaret)} {D(no)} "
        satir += (B(etiket) if i == secili else etiket)
        if aciklama:
            satir += "  " + D("— " + aciklama)
        print(satir)
    hr()
    if esc_uyari:
        print("  " + Y("Çıkmak için bir kez daha Esc'ye basın"))
    else:
        print("  " + D(_MENU_IPUCU))


def menu_loop(baslik, ogeler, yol=None, ana=False):
    """ogeler: [(etiket, aciklama, callable|None [, alt_menu_mu])].
    callable None ise 'Geri'/'Çıkış' demektir. Döner çıkış kodu (int)."""
    yol = list(yol or [baslik])
    if not _interactive():
        return _menu_basit(baslik, ogeler, yol)
    secili = 0
    n = len(ogeler)
    esc_say = 0  # ana menüde ard arda Esc sayacı: 2 kez -> çıkış
    while True:
        _draw(baslik, ogeler, secili, yol, esc_uyari=(ana and esc_say == 1))
        try:
            k = _read_key()
        except KeyboardInterrupt:
            if ana:
                esc_say = 0
                secili = n - 1  # Çıkış'a taşı, çıkma
                continue
            return 0
        if k != "esc":
            esc_say = 0
        if k == "up":
            secili = (secili - 1) % n
        elif k == "down":
            secili = (secili + 1) % n
        elif k and k.isdigit() and 1 <= int(k) <= n:
            secili = int(k) - 1
            r = _sec(ogeler[secili], yol)
            if r == "geri":
                return 0
        elif k == "enter":
            r = _sec(ogeler[secili], yol)
            if r == "geri":
                return 0
        elif k == "esc":
            if not ana:
                return 0        # alt menü: üst menüye dön (tek Esc)
            esc_say += 1
            if esc_say >= 2:
                return 0        # ana menü: 2. Esc -> çıkış
            secili = n - 1      # 1. Esc: Çıkış'ı işaretle + uyarı göster


def _sec(oge, yol):
    etiket, _aciklama, *rest = oge
    fn = rest[0] if rest else None
    if fn is None:
        return "geri"
    print("\033[2J\033[H", end="")
    try:
        fn()
    except KeyboardInterrupt:
        print()
    except SystemExit:
        pass
    try:
        ask("\n  " + D("Devam etmek için Enter..."))
    except EOFError:
        pass
    return None


def _menu_basit(baslik, ogeler, yol):
    """tty yoksa numaralı basit menü."""
    while True:
        print()
        print("  " + baslik)
        for i, (etiket, aciklama, *_r) in enumerate(ogeler, 1):
            print(f"  {i}) {etiket}" + (f"  — {aciklama}" if aciklama else ""))
        try:
            s = ask("  Seçim: ").strip()
        except EOFError:
            return 0
        if not s.isdigit() or not (1 <= int(s) <= len(ogeler)):
            continue
        r = _sec(ogeler[int(s) - 1], yol)
        if r == "geri":
            return 0
