# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Ön kurulum denetimi ve otomatik kurulum.

Düz bir Windows'ta aracın çalışması için gerekenleri başlangıçta KATMANLI denetler
ve mümkün olanı kendisi tamamlar:

  1. Yönetici (Administrator) hakkı
  2. Python sürümü
  3. CHIPSEC Python paketi kurulu mu (import edilebiliyor mu)
  4. CHIPSEC SPI gerçekten çalışıyor mu (çekirdek sürücüsü yüklenip descriptor
     okunabiliyor mu) — asıl kapı budur
  5. Secure Boot / .NET / C derleyici gibi yardımcı koşullar

Windows'ta önemli gerçek (deneyle doğrulanmıştır):
  - PyPI'deki `chipsec` paketi ÖNCEDEN DERLENMİŞ ÇEKİRDEK SÜRÜCÜSÜ İÇERMEZ
    (paketin içindeki README.NO_KERNEL_DRIVER bunu açıkça söyler). Yani düz
    `pip install chipsec` kurulsa bile SPI okuma/yazma, sürücü ayrıca
    sağlanmadıkça çalışmaz.
  - Üstelik `pip install chipsec` kaynaktan `EfiCompressor` adlı bir C uzantısı
    derler ve bunun için Microsoft Visual C++ Build Tools (cl.exe) gerekir —
    temiz bir tahtada bu yoktur, dolayısıyla kurulum baştan patlar. Oysa
    EfiCompressor yalnız UEFI sıkıştırma modülleri içindir; SPI oku/yaz için
    GEREKMEZ. Bu yüzden bu araç chipsec'i, uzantıyı DEVRE DIŞI bırakarak
    (derleyici istemeden) kurar.
  - SPI erişimi için çekirdek sürücüsü iki yoldan sağlanır:
      (a) RWEverything'in WHQL-imzalı RwDrv.sys sürücüsü + chipsec'in `rwe`
          yardımcısı  (derleme/.NET gerektirmez; yalnız Secure Boot kapalı
          olmalı — bu tahtalarda kapalıdır),
      (b) chipsec'in kendi sürücüsünü kaynaktan Visual Studio + WDK + MSBuild
          (.NET Framework) ile derleyip imzalamak.
    Araç her ikisini de açıkça yönlendirir; otomatikleştirebildiğini (paket
    kurulumu) otomatik yapar, donanım/sürücü adımını komutlarıyla gösterir.

Yalnız okuma işlevleri (wkey read, mac read) CHIPSEC gerektirmez.
"""

import os
import re
import sys
import subprocess

from . import ui, flash
from .ui import (B, R, G, Y, D, OK, WARN, ERR)


MIN_PY = (3, 7)

# chipsec kurulurken SPI için gereksiz olan ve MSVC isteyen C uzantısı.
_SKIP_EXT = "EfiCompressor"


def python_ok():
    return sys.version_info[:2] >= MIN_PY


def admin():
    return ui.is_admin()


def chipsec_installed():
    """CHIPSEC Python paketi import edilebiliyor mu."""
    try:
        import importlib.util
        return importlib.util.find_spec("chipsec") is not None
    except Exception:
        return False


def chipsec_util_ok():
    """chipsec_util çağrılabiliyor mu (paket + giriş noktası yerinde mi).
    Bu, SÜRÜCÜNÜN yüklendiği anlamına GELMEZ; yalnız aracı çalıştırabiliyoruz."""
    return flash.available()


def spi_ready():
    """SPI gerçekten çalışıyor mu: sürücü yüklenip flash descriptor okunabiliyor mu.
    Döner (ok: bool, detay: str). Yönetici ister; çekirdek sürücüsünü yükler
    (salt-okunur bir sorgudur, flash'a yazmaz)."""
    if not admin():
        return False, "yönetici değil (sürücü yüklenemez)"
    return flash.spi_probe()


def compiler_present():
    """pip'in chipsec'i kaynaktan derleyebilmesi için MSVC var mı (bilgi amaçlı)."""
    from shutil import which
    if which("cl") or which("cl.exe"):
        return True
    vswhere = os.path.expandvars(
        r"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe")
    if os.path.exists(vswhere):
        try:
            r = subprocess.run(
                [vswhere, "-latest", "-products", "*",
                 "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                 "-property", "installationPath"],
                capture_output=True, text=True, timeout=30)
            return bool((r.stdout or "").strip())
        except Exception:
            return False
    return False


def dotnet4_release():
    """Kurulu .NET Framework 4.x 'Release' numarası (yoksa None).
    chipsec'in KENDİ sürücüsünü WDK/MSBuild ile derlemek isteyenler için gerekir;
    RwDrv yolunda gerekmez."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as k:
            val, _ = winreg.QueryValueEx(k, "Release")
            return int(val)
    except Exception:
        return None


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


# ===================== CHIPSEC kurulumu (derleyici gerektirmez) =====================
def _pip(args, timeout=1800):
    return subprocess.run([sys.executable, "-m", "pip"] + args,
                          capture_output=True, text=True, timeout=timeout)


def _tail(r, n=6):
    out = (r.stdout or "") + (r.stderr or "")
    return "\n".join(out.strip().splitlines()[-n:])


def _install_chipsec_nocompile():
    """chipsec'i EfiCompressor C uzantısı olmadan kaynaktan kurar (MSVC istemez).
    sdist'i indirir, setup.py içindeki ext_modules'ü boşaltır, kurar.
    Döner (ok, mesaj)."""
    import tempfile
    import glob
    import tarfile
    import shutil

    work = tempfile.mkdtemp(prefix="eta112_chipsec_")
    try:
        # 1) kaynak dağıtımı indir
        r = _pip(["download", "chipsec", "--no-deps", "--no-binary=:all:",
                  "--dest", work], timeout=900)
        if r.returncode != 0:
            return False, "chipsec kaynağı indirilemedi:\n" + _tail(r)
        tars = glob.glob(os.path.join(work, "chipsec-*.tar.gz"))
        if not tars:
            return False, "chipsec kaynak arşivi bulunamadı"
        # 2) aç
        src_root = os.path.join(work, "src")
        os.makedirs(src_root, exist_ok=True)
        with tarfile.open(tars[0]) as tf:
            # güvenli çıkarma (yol kaçışlarını ele)
            for m in tf.getmembers():
                p = os.path.normpath(os.path.join(src_root, m.name))
                if not p.startswith(os.path.normpath(src_root) + os.sep):
                    return False, "arşivde güvensiz yol: " + m.name
            tf.extractall(src_root)
        pkgdirs = [d for d in glob.glob(os.path.join(src_root, "chipsec-*"))
                   if os.path.isdir(d)]
        if not pkgdirs:
            return False, "açılan chipsec kaynağı bulunamadı"
        pkg = pkgdirs[0]
        setup_py = os.path.join(pkg, "setup.py")
        # 3) EfiCompressor uzantısını devre dışı bırak
        if os.path.exists(setup_py):
            with open(setup_py, "r", encoding="utf-8") as f:
                txt = f.read()
            patched = txt.replace("ext_modules=extra_kw",
                                  "ext_modules=[]  # eta112win: EfiCompressor kapalı")
            if patched == txt:
                # beklenmedik setup biçimi — yine de denemeye değer, uyar
                patched = re.sub(r"ext_modules\s*=\s*extra_kw", "ext_modules=[]", txt)
            with open(setup_py, "w", encoding="utf-8") as f:
                f.write(patched)
        # 4) kur (derleme yok)
        r = _pip(["install", "--no-build-isolation", pkg], timeout=1800)
        if r.returncode != 0:
            # setuptools/wheel eksikse bir kez tamamlayıp yeniden dene
            _pip(["install", "--upgrade", "setuptools", "wheel"], timeout=600)
            r = _pip(["install", "--no-build-isolation", pkg], timeout=1800)
        if r.returncode != 0:
            return False, "chipsec kurulamadı (uzantısız):\n" + _tail(r)
        return True, "chipsec kuruldu (EfiCompressor olmadan; SPI için yeterli)"
    except Exception as e:
        return False, "chipsec kurulum hatası: %s" % e
    finally:
        try:
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass


def pip_install_chipsec():
    """CHIPSEC Python paketini kurar. Önce derleyici varsa düz pip; yoksa (ya da
    düz kurulum MSVC yüzünden patlarsa) EfiCompressor'suz kaynak kurulumu.
    Döner (ok, mesaj)."""
    # pywin32 Windows'ta chipsec'in bağımlılığı — wheel olarak gelir
    if compiler_present():
        r = _pip(["install", "--upgrade", "chipsec"])
        if r.returncode == 0:
            return True, "chipsec kuruldu (pip)"
        tail = _tail(r)
        if "Visual C++" not in tail and "EfiCompressor" not in tail and "cl.exe" not in tail:
            return False, "chipsec kurulamadı:\n" + tail
        # derleyici 'var' görünse de uzantı patladı -> uzantısız dene
    # derleyici yok ya da uzantı derlemesi patladı: uzantısız kur
    return _install_chipsec_nocompile()


# ===================== raporlama =====================
def status(probe_spi=False):
    """Tüm önkoşulların anlık durumunu sözlük olarak döner.
    probe_spi=True ise sürücüyü yükleyip SPI'yi gerçekten dener (yönetici gerekir)."""
    inst = chipsec_installed()
    util = chipsec_util_ok() if inst else False
    spi_ok, spi_detail = (spi_ready() if (probe_spi and util) else (None, None))
    return {
        "python": python_ok(),
        "python_version": "%d.%d.%d" % sys.version_info[:3],
        "admin": admin(),
        "chipsec_installed": inst,
        "chipsec_util": util,
        "spi_ready": spi_ok,
        "spi_detail": spi_detail,
        "secure_boot": secure_boot(),
        "compiler": compiler_present(),
        "dotnet4": dotnet4_release() is not None,
        "windows": sys.platform == "win32",
    }


def report(flash_needed=False, probe_spi=False):
    """Durumu okunur biçimde yazar. Döner: temel koşullar sağlanıyor mu (bool)."""
    st = status(probe_spi=probe_spi)
    print(B("\n  Ön kurulum denetimi"))

    def line(lbl, ok_, detail, warn_only=False):
        mark = OK if ok_ else (WARN if warn_only else ERR)
        print(f"  {mark} {lbl:<24}{D(detail)}")

    line("Windows", st["windows"], "" if st["windows"] else "bu araç Windows içindir")
    line("Python " + st["python_version"], st["python"],
         "" if st["python"] else "Python %d.%d+ gerekir" % MIN_PY)
    line("Yönetici (Admin)", st["admin"],
         "" if st["admin"] else "flash/MSDM işlemleri için gerekir")

    # CHIPSEC paketi
    if st["chipsec_installed"]:
        line("CHIPSEC paketi", st["chipsec_util"],
             "kurulu ve çalıştırılabilir" if st["chipsec_util"]
             else "kurulu ama chipsec_util çalışmadı", warn_only=not st["chipsec_util"])
    else:
        line("CHIPSEC paketi", False,
             "kurulu değil — araç kendisi kurabilir (derleyici gerekmez)", warn_only=True)

    # Asıl kapı: SPI sürücüsü
    if st["spi_ready"] is True:
        line("SPI sürücüsü", True, st.get("spi_detail") or "flash erişimi hazır")
    elif st["spi_ready"] is False:
        line("SPI sürücüsü", False,
             (st.get("spi_detail") or "sürücü yüklenemedi") +
             " — RwDrv.sys (rwe) ya da WDK ile derlenmiş sürücü gerekir", warn_only=True)
    else:
        line("SPI sürücüsü", False,
             "denenmedi (kontrol komutu sürücüyü yükleyerek sınar)", warn_only=True)

    # Secure Boot
    sb = st["secure_boot"]
    if sb is True:
        line("Secure Boot", False,
             "AÇIK — SPI sürücüsü yüklenemez; kapatın ya da test imzalama açın", warn_only=True)
    elif sb is False:
        line("Secure Boot", True, "kapalı — SPI sürücüsü yüklenebilir")
    else:
        line("Secure Boot", True, "yok/legacy (UEFI değil) — sorun değil")

    # Yardımcılar (yalnız chipsec'i kendi sürücüsüyle derlemek isteyenler için)
    if not st["chipsec_util"]:
        line("C++ Build Tools", st["compiler"],
             "var" if st["compiler"] else "yok — gerekmez (uzantısız kurulum kullanılır)",
             warn_only=not st["compiler"])
    if st["spi_ready"] is not True:
        line(".NET Framework 4.x", st["dotnet4"],
             "var" if st["dotnet4"] else
             "yok — yalnız chipsec sürücüsünü WDK ile DERLEYECEKSENİZ gerekir",
             warn_only=not st["dotnet4"])

    base_ok = st["windows"] and st["python"]
    if flash_needed:
        return base_ok and st["admin"] and (st["spi_ready"] is True)
    return base_ok


def _driver_help():
    """SPI sürücüsünü sağlamak için somut yönlendirme."""
    print(D("\n  SPI (BIOS flash) erişimi için çekirdek sürücüsü gerekir. İki yol:"))
    print("  " + B("A) RWEverything sürücüsü (önerilir — derleme/.NET gerekmez):"))
    print(D("     1. https://rweverything.com adresinden Read & Write Utility'yi indirin,"))
    print(D("        içinden RwDrv.sys dosyasını çıkarın."))
    print(D("     2. RwDrv.sys'i chipsec'in rwe klasörüne koyun, ör.:"))
    print(D("        <python>\\Lib\\site-packages\\chipsec\\helper\\rwe\\windows_amd64\\RwDrv.sys"))
    print(D("     3. chipsec'i rwe yardımcısıyla çağırın (araç ETA112_CHIPSEC ile ezilebilir):"))
    print(D('        setx ETA112_CHIPSEC "python -m chipsec_util -i -n --helper rwe"'))
    print("  " + B("B) chipsec'in kendi sürücüsünü derleyin:"))
    print(D("     Visual Studio + WDK + .NET Framework (MSBuild) ile chipsec kaynağından"))
    print(D("     sürücüyü derleyip imzalayın (chipsec-manual.pdf). Secure Boot kapalı olmalı."))


# ===================== otomatik kurulum =====================
def ensure_chipsec(interactive=True, auto=False, need_spi=True):
    """CHIPSEC hazır değilse kurmayı/yönlendirmeyi dener. Döner (ok, mesaj).

    need_spi=True: 'hazır' demek SPI sürücüsünün gerçekten yüklenebilmesidir
    (bios read/set/clear için şart). need_spi=False: yalnız paket yeterli."""
    if not need_spi:
        if chipsec_util_ok():
            return True, "CHIPSEC paketi hazır"

    # 1) Paketi kur (gerekiyorsa)
    if not chipsec_util_ok():
        if not admin():
            return False, "CHIPSEC kurulumu için yönetici (Administrator) gerekir"
        if interactive and not auto:
            if not ui.confirm_eh(
                    "CHIPSEC kurulu değil. Şimdi kurulsun mu (derleyici gerekmez)?",
                    default_no=False):
                return False, "kurulum iptal edildi"
        if not ui.JSON:
            print(D("  CHIPSEC kuruluyor (EfiCompressor olmadan)... birkaç dakika sürebilir."),
                  flush=True)
        ok, msg = pip_install_chipsec()
        if not ok:
            return False, msg
        if not chipsec_util_ok():
            return False, "CHIPSEC kuruldu ama chipsec_util çalıştırılamadı: " + msg

    if not need_spi:
        return True, "CHIPSEC paketi hazır"

    # 2) SPI sürücüsü gerçekten çalışıyor mu?
    if not admin():
        return False, "SPI erişimi için yönetici (Administrator) gerekir"
    spi_ok, detail = flash.spi_probe()
    if spi_ok:
        return True, "CHIPSEC SPI hazır (" + detail + ")"

    sb = secure_boot()
    if sb is True:
        return False, ("CHIPSEC var ama SPI sürücüsü yüklenemiyor — Secure Boot AÇIK. "
                       "Kapatın (ya da test imzalama açın) ve yeniden deneyin.")
    # paket var, Secure Boot kapalı, ama sürücü yok -> yönlendir
    if interactive and not ui.JSON:
        _driver_help()
    return False, ("CHIPSEC paketi kurulu ama SPI çekirdek sürücüsü bulunamadı (" +
                   (detail or "sürücü yüklenemedi") + "). Yukarıdaki A/B yolunu izleyin.")


def startup(auto_install=True, interactive=True):
    """Başlangıç denetimi: durumu yazar, CHIPSEC paketi eksikse (yönetici +
    etkileşimli ise) kurmayı önerir. Sürücü yüklemeyi başlangıçta DENEMEZ
    (yan etkili); yalnız bilgilendirir. Okuma işlevlerini engellemez."""
    if sys.platform != "win32":
        return
    report(flash_needed=False, probe_spi=False)
    if auto_install and interactive and admin() and not chipsec_util_ok():
        print()
        ok, msg = ensure_chipsec(interactive=True, auto=False, need_spi=False)
        print(f"  {OK if ok else WARN} {msg}")
