# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Komut satırı dağıtımı ve etkileşimli menü.

Kullanım:
  eta-112-win.py                      # etkileşimli menü
  eta-112-win.py bios read|set|clear|info|calibrate [--json] [--dump DOSYA]
  eta-112-win.py mac  read|check <MAC>|set <MAC> [--json]
  eta-112-win.py wkey read|set <ANAHTAR> [--json]
"""

import sys

from . import ui
from .ui import (B, R, G, Y, Cy, D, emit)
from . import bios, mac, wkey, preflight, feedback
from .profiles import PROFILES


class _A:
    pass


def _pop_json(args):
    if "--json" in args:
        ui.set_json(True)
        return [x for x in args if x != "--json"]
    return args


def _opt(args, name):
    """--name VALUE ayıklar; (value|None, kalan_args)."""
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1], args[:i] + args[i + 2:]
    return None, args


# ===================== BIOS =====================
def bios_main(argv):
    args = _pop_json(list(argv))
    if args and args[0] in ("-h", "--help", "yardim"):
        print(B("eta-112-win bios") + " — BIOS yönetici/kullanıcı parolası")
        print("  bios read                 # parolaları oku (varsayılan)")
        print("  bios info                 # model / destek bilgisi")
        print("  bios set [--yonetici P] [--kullanici P] [--koruma setup|always]")
        print("  bios clear <all|yonetici|kullanici>")
        print("  bios calibrate <yonetici|kullanici> <PAROLA>")
        print(D("  --dump DOSYA: canlı flash yerine bir ROM dökümünden oku (yazma yok)"))
        print(D("  --out DOSYA : (set/clear) donanıma YAZMADAN düzenlenmiş imajı dosyaya"))
        print(D("               yaz — dry-run; --dump ile birlikte kullanılır, brick riski yok"))
        print(D("  --json      : makine-okur çıktı"))
        return 0
    cmd = args[0] if args else "read"
    rest = args[1:]
    dump, rest = _opt(rest, "--dump")
    out, rest = _opt(rest, "--out")
    if cmd in ("info",):
        return bios.cmd_info(_A()) or 0
    if cmd in ("read", "oku"):
        a = _A(); a.dump = dump
        return bios.cmd_read(a) or 0
    if cmd in ("calibrate", "kalibrasyon"):
        if len(rest) < 2:
            return emit({"ok": False, "error": "slot ve parola gerekli"}, 1) if ui.JSON else \
                (print(R("  Kullanım: bios calibrate <yonetici|kullanici> <PAROLA>")) or 1)
        a = _A(); a.slot = rest[0]; a.password = rest[1]; a.dump = dump
        return bios.cmd_calibrate(a) or 0
    if cmd in ("set", "ayarla"):
        yon, rest = _opt(rest, "--yonetici")
        kul, rest = _opt(rest, "--kullanici")
        kor, rest = _opt(rest, "--koruma")
        a = _A(); a.yonetici = yon; a.kullanici = kul; a.koruma = kor
        a.dump = dump; a.out = out
        return bios.cmd_set(a) or 0
    if cmd in ("clear", "temizle"):
        if not rest or rest[0] not in ("all", "yonetici", "kullanici"):
            return emit({"ok": False, "error": "slot gerekli"}, 1) if ui.JSON else \
                (print(R("  Kullanım: bios clear <all|yonetici|kullanici>")) or 1)
        a = _A(); a.slot = rest[0]; a.dump = dump; a.out = out
        return bios.cmd_clear(a) or 0
    ui.die("Bilinmeyen bios komutu: %s   (read|set|clear|info|calibrate)" % cmd)


# ===================== MAC =====================
def mac_main(argv):
    args = _pop_json(list(argv))
    if args and args[0] in ("-h", "--help", "yardim"):
        print(B("eta-112-win mac") + " — onboard ethernet MAC oku / doğrula / (değiştir)")
        print("  mac read            # MAC(ler) + Faz OUI durumu (varsayılan)")
        print("  mac check <MAC>     # yazmadan önce sına: biçim, tür ve Faz OUI")
        print("  mac set <MAC>       # Windows'ta eFuse yazma Realtek PG aracı gerektirir")
        print(D("  --json            : makine-okur çıktı"))
        return 0
    cmd = args[0] if args else "read"
    if cmd in ("read", "oku"):
        return mac.cmd_mac_read(_A()) or 0
    if cmd in ("check", "dogrula", "validate", "kontrol"):
        if len(args) < 2:
            return emit({"ok": False, "error": "mac argümanı gerekli"}, 1) if ui.JSON else \
                (print(R("  Kullanım: mac check <MAC>")) or 1)
        a = _A(); a.mac = args[1]
        return mac.cmd_mac_check(a) or 0
    if cmd in ("set", "write", "yaz"):
        if len(args) < 2:
            return emit({"ok": False, "error": "mac argümanı gerekli"}, 1) if ui.JSON else \
                (print(R("  Kullanım: mac set <MAC>")) or 1)
        a = _A(); a.mac = args[1]
        return mac.cmd_mac_set(a) or 0
    ui.die("Bilinmeyen mac komutu: %s   (read|check|set)" % cmd)


# ===================== WKEY =====================
def wkey_main(argv):
    args = _pop_json(list(argv))
    if args and args[0] in ("-h", "--help", "yardim"):
        print(B("eta-112-win wkey") + " — BIOS'taki Windows ürün anahtarı (ACPI MSDM)")
        print("  wkey read           # anahtarı göster (sürücüsüz)")
        print("  wkey set <ANAHTAR>  # flash'taki MSDM anahtarını değiştir (CHIPSEC)")
        print(D("  --json            : makine-okur çıktı"))
        return 0
    cmd = args[0] if args else "read"
    if cmd in ("read", "oku"):
        return wkey.cmd_wkey_read(_A()) or 0
    if cmd in ("set", "write", "yaz", "degistir"):
        if len(args) < 2:
            return emit({"ok": False, "error": "anahtar gerekli"}, 1) if ui.JSON else \
                (print(R("  Kullanım: wkey set <ANAHTAR>")) or 1)
        a = _A(); a.key = args[1]
        return wkey.cmd_wkey_set(a) or 0
    ui.die("Bilinmeyen wkey komutu: %s   (read|set)" % cmd)


# ===================== yardım =====================
def usage():
    rule = D("─" * 60)
    print()
    print("  " + B(Cy("ETA-112-WIN")) + " — " + B("Windows BIOS/EEPROM Aracı") + "   " + D("BIOS · MAC · Windows anahtarı"))
    print("  " + D("eta-112'nin Windows portu · desteklenen modeller: ")
          + D(", ".join(sorted({p['model_name'] for p in PROFILES.values()}))))
    print()
    print(rule)
    print(B("  KULLANIM"))
    print("  " + D("eta-112-win.py") + "                      " + D("→ etkileşimli menü"))
    print("  " + D("eta-112-win.py ") + G("bios") + " " + D("<komut>") + "       " + D("→ BIOS parolası (read·set·clear·info·calibrate)"))
    print("  " + D("eta-112-win.py ") + G("mac") + " " + D("<komut>") + "        " + D("→ ethernet MAC (read·check·set)"))
    print("  " + D("eta-112-win.py ") + G("wkey") + " " + D("<komut>") + "       " + D("→ Windows ürün anahtarı (read·set)"))
    print("  " + D("eta-112-win.py ") + G("kontrol") + "              " + D("→ ön kurulum denetimi + CHIPSEC otomatik kurulum"))
    print("  " + D("her komut için ayrıntı: ") + G("eta-112-win.py <komut> -h"))
    print(rule)
    print("  " + Y("Yazma işlemleri (bios set/clear, wkey set) CHIPSEC gerektirir ve"))
    print("  " + Y("Windows portunda donanımda DOĞRULANMAMIŞTIR — brick riski."))
    print(rule)


# ===================== menü =====================
def _bios_menu():
    return ui.menu_loop("BIOS parolası", [
        ("Parolaları oku", "", lambda: bios_main(["read"])),
        ("Parola ayarla", "", lambda: bios_main(["set"])),
        ("Parola temizle", "", _bios_temizle),
        ("Model / destek bilgisi", "", lambda: bios_main(["info"])),
        ("Geri", "", None),
    ], yol=["ETA-112-WIN", "BIOS EEPROM", "BIOS parolası"])


def _bios_temizle():
    slot = ui.ask("  Hangi parola silinsin? [all/yonetici/kullanici]: ").strip() or "all"
    if slot not in ("all", "yonetici", "kullanici"):
        slot = "all"
    return bios_main(["clear", slot])


def _mac_menu():
    return ui.menu_loop("MAC adresi", [
        ("MAC oku", "güncel adresler ve Faz OUI durumu", lambda: mac_main(["read"])),
        ("MAC doğrula", "yazmadan önce sına — donanıma dokunmaz",
         lambda: mac_main(["check", ui.ask("  Doğrulanacak MAC: ").strip()])),
        ("MAC değiştir", "Windows'ta Realtek PG aracı gerekir",
         lambda: mac_main(["set", ui.ask("  Yeni MAC: ").strip()])),
        ("Geri", "", None),
    ], yol=["ETA-112-WIN", "BIOS EEPROM", "MAC adresi"])


def _wkey_menu():
    return ui.menu_loop("Windows ürün anahtarı", [
        ("Anahtarı oku", "", lambda: wkey_main(["read"])),
        ("Anahtarı değiştir", "",
         lambda: wkey_main(["set", ui.ask("  Yeni anahtar (XXXXX-XXXXX-XXXXX-XXXXX-XXXXX): ").strip()])),
        ("Geri", "", None),
    ], yol=["ETA-112-WIN", "BIOS EEPROM", "Windows ürün anahtarı"])


def _bios_eeprom_menu():
    return ui.menu_loop("BIOS EEPROM", [
        ("BIOS parolası", "", _bios_menu),
        ("MAC adresi", "", _mac_menu),
        ("Windows ürün anahtarı", "", _wkey_menu),
        ("Geri", "", None),
    ], yol=["ETA-112-WIN", "BIOS EEPROM"])


def kontrol_main(argv):
    args = _pop_json(list(argv))
    if ui.JSON:
        # JSON (otomasyon) kipinde sürücü yüklemeyiz (yan etkisiz, hızlı).
        return emit({"ok": True, **preflight.status(probe_spi=False)})
    # Etkileşimli denetim: chipsec kuruluysa SPI'yi gerçekten sına (sürücüyü yükler).
    probe = preflight.admin() and preflight.chipsec_util_ok()
    ok = preflight.report(flash_needed=False, probe_spi=probe)
    if preflight.admin() and not preflight.chipsec_util_ok():
        print()
        cok, msg = preflight.ensure_chipsec(interactive=True, auto=False, need_spi=False)
        print(f"  {ui.OK if cok else ui.WARN} {msg}")
    return 0 if ok else 1


def menu():
    preflight.startup(auto_install=True, interactive=True)
    rc = ui.menu_loop("ETA-112-WIN", [
        ("BIOS EEPROM", "BIOS parolası · MAC · Windows anahtarı", _bios_eeprom_menu),
        ("Ön kurulum denetimi", "Python · CHIPSEC · Secure Boot; eksikse kur", lambda: kontrol_main([])),
        ("Çıkış", "", None),
    ], yol=["ETA-112-WIN"], ana=True)
    # Ana menüden çıkış: geliştiriciye (Özgür Koca) geri bildirim sor (ntfy -> eta-112)
    feedback.exit_feedback()
    return rc


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.platform != "win32" and not ("--dump" in argv or "-h" in argv or "--help" in argv):
        ui.warn("Bu araç Windows içindir. Linux'ta yalnız --dump ile okuma ve -h çalışır "
                "(canlı flash/MAC/MSDM erişimi yoktur).")
    if argv and argv[0] in ("--help", "-h", "help", "yardim"):
        usage()
        return 0
    if argv and argv[0] in ("bios", "firmware", "uefi"):
        return bios_main(argv[1:]) or 0
    if argv and argv[0] in ("mac", "ethernet", "eth"):
        return mac_main(argv[1:]) or 0
    if argv and argv[0] in ("wkey", "windows", "winkey", "seri"):
        return wkey_main(argv[1:]) or 0
    if argv and argv[0] in ("kontrol", "doctor", "onkurulum", "check-deps"):
        return kontrol_main(argv[1:]) or 0
    if argv:
        ui.die("Bilinmeyen komut: %s   ('eta-112-win.py --help')" % argv[0])
    return menu()


def entry():
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        print()
        ui.die("Kullanıcı iptali.", 130)
    except EOFError:
        ui.die("Girdi alınamadı (tty yok).", 1)
