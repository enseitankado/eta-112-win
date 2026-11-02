# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Ön kurulum denetimi ve otomatik kurulum.

Düz bir Windows'ta aracın çalışması için gerekenleri başlangıçta denetler ve
mümkünse kendisi tamamlar:
  - Yönetici (Administrator) hakkı
  - Python sürümü
  - CHIPSEC (SPI flash okuma/yazma için) — yoksa 'pip install chipsec' ile kurar
  - Secure Boot / UEFI durumu (CHIPSEC sürücüsü yüklenebilir mi)

Yalnız okuma işlevleri (wkey read, mac read) CHIPSEC gerektirmez; bu yüzden CHIPSEC
kurulumu yalnız gerektiğinde (flash işlemi öncesi) ya da kullanıcı onayıyla yapılır.
"""

import sys
import subprocess

from . import ui, flash
from .ui import (B, R, G, Y, D, OK, WARN, ERR)


MIN_PY = (3, 7)


def python_ok():
    return sys.version_info[:2] >= MIN_PY


def admin():
    return ui.is_admin()


def chipsec_installed():
    try:
        import importlib.util
        return importlib.util.find_spec("chipsec") is not None
    except Exception:
        return False


def chipsec_runnable():
    """CHIPSEC çalıştırılabiliyor mu (chipsec_util yanıt veriyor mu)."""
    return flash.available()


def pip_install_chipsec():
    """'pip install chipsec' dener. Döner (ok, son_satırlar)."""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "chipsec"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except Exception as e:
        return False, str(e)
    out = (r.stdout or "") + (r.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-4:])
    return r.returncode == 0, tail


def secure_boot():
    """Secure Boot durumu: True=açık, False=kapalı, None=yok/legacy(UEFI değil)."""
    ps = "try { if (Confirm-SecureBootUEFI) { 'ON' } else { 'OFF' } } catch { 'NA' }"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    s = (r.stdout or "").strip().upper()
    if "ON" in s:
        return True
    if "OFF" in s:
        return False
    return None


# ===================== raporlama =====================
def status():
    """Tüm önkoşulların anlık durumunu sözlük olarak döner."""
    inst = chipsec_installed()
    return {
        "python": python_ok(),
        "python_version": "%d.%d.%d" % sys.version_info[:3],
        "admin": admin(),
        "chipsec_installed": inst,
        "chipsec_runnable": chipsec_runnable() if inst else False,
        "secure_boot": secure_boot(),
        "windows": sys.platform == "win32",
    }


def report(flash_needed=False):
    """Durumu okunur biçimde yazar. Döner: temel koşullar sağlanıyor mu (bool)."""
    st = status()
    print(B("\n  Ön kurulum denetimi"))

    def line(lbl, ok_, detail, warn_only=False):
        mark = OK if ok_ else (WARN if warn_only else ERR)
        print(f"  {mark} {lbl:<22}{D(detail)}")

    line("Windows", st["windows"], "" if st["windows"] else "bu araç Windows içindir")
    line("Python " + st["python_version"], st["python"],
         "" if st["python"] else "Python %d.%d+ gerekir" % MIN_PY)
    line("Yönetici (Admin)", st["admin"],
         "" if st["admin"] else "flash/MSDM işlemleri için gerekir")
    if st["chipsec_installed"]:
        line("CHIPSEC", st["chipsec_runnable"],
             "kurulu ve çalışıyor" if st["chipsec_runnable"]
             else "kurulu ama çalıştırılamadı (sürücü/Secure Boot?)", warn_only=True)
    else:
        line("CHIPSEC", False, "kurulu değil — SPI flash okuma/yazma için gerekir", warn_only=True)
    sb = st["secure_boot"]
    if sb is True:
        line("Secure Boot", False,
             "AÇIK — CHIPSEC sürücüsü yüklenemez; kapatın ya da test imzalama açın", warn_only=True)
    elif sb is False:
        line("Secure Boot", True, "kapalı — CHIPSEC sürücüsü yüklenebilir")
    else:
        line("Secure Boot", True, "yok/legacy (UEFI değil) — sorun değil")

    base_ok = st["windows"] and st["python"]
    if flash_needed:
        return base_ok and st["admin"] and st["chipsec_runnable"]
    return base_ok


# ===================== otomatik kurulum =====================
def ensure_chipsec(interactive=True, auto=False):
    """CHIPSEC hazır değilse kurmayı dener. Döner (ok, mesaj)."""
    if chipsec_runnable():
        return True, "CHIPSEC hazır"
    if not admin():
        return False, "CHIPSEC için yönetici (Administrator) gerekir"
    if not chipsec_installed():
        if interactive and not auto:
            if not ui.confirm_eh("CHIPSEC kurulu değil. Şimdi 'pip install chipsec' ile kurulsun mu?",
                                 default_no=False):
                return False, "kurulum iptal edildi"
        if not ui.JSON:
            print(D("  CHIPSEC kuruluyor (pip install chipsec)... bu birkaç dakika sürebilir."), flush=True)
        ok, tail = pip_install_chipsec()
        if not ok:
            return False, "CHIPSEC kurulamadı:\n" + tail
    # kurulduktan sonra çalışabiliyor mu?
    if chipsec_runnable():
        return True, "CHIPSEC kuruldu ve çalışıyor"
    sb = secure_boot()
    if sb is True:
        return False, ("CHIPSEC kurulu ama sürücü yüklenemiyor — Secure Boot AÇIK. "
                       "Kapatın (ya da test imzalama açın) ve yeniden deneyin.")
    return False, "CHIPSEC kurulu ama çalıştırılamadı (sürücü yüklenemedi)"


def startup(auto_install=True, interactive=True):
    """Başlangıç denetimi: durumu yazar, CHIPSEC eksikse (yönetici + etkileşimli ise)
    kurmayı önerir. Yalnız bilgilendirir — okuma işlevlerini engellemez."""
    if sys.platform != "win32":
        return
    report(flash_needed=False)
    if auto_install and interactive and admin() and not chipsec_runnable():
        print()
        ok, msg = ensure_chipsec(interactive=True, auto=False)
        print(f"  {OK if ok else WARN} {msg}")
