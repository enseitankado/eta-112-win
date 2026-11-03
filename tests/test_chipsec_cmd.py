# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""chipsec_util çağrısı: modül adı çözümü ve 'available' tespiti.

Gerçek chipsec/donanım gerekmez; flash.subprocess.run taklit edilir. Regresyon
kilidi: 'No module named chipsec_util' hatası BAŞARI sayılmamalı (eski bug);
CHIPSEC afişindeki zararsız 'No module named ...' satırları BAŞARIYI bozmamalı.
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eta112win import flash  # noqa: E402


class _R:
    def __init__(self, rc, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def _patch_run(fn):
    flash.subprocess.run = fn
    flash.reset_cmd_cache()


# ---- available() ----
def test_available_modul_yok_basarisizlik():
    # '-m chipsec_util' modülü bulamayınca Python rc!=0 + 'No module named' verir;
    # afiş HİÇ çıkmaz. Bu BAŞARISIZLIKTIR (eski kod yanlışlıkla True döndürüyordu).
    _patch_run(lambda *a, **k: _R(
        1, err="C:\\Python312\\python.exe: No module named chipsec_util\n"))
    assert flash.available() is False


def test_available_afis_rc0_basari():
    out = ("[CHIPSEC] Version  : 1.13.16\n"
           "usage: chipsec_util.py [options] <command>\n")
    _patch_run(lambda *a, **k: _R(0, out=out))
    assert flash.available() is True


def test_available_zararsiz_import_hatasi_basari():
    # CHIPSEC afişi + zararsız 'No module named chipsec.library.tpm' + rc0 -> BAŞARI
    out = ("ERROR: Exception occurred during import of tpm_cmd: "
           "'No module named 'chipsec.library.tpm''\n"
           "[CHIPSEC] Version  : 1.13.16\n"
           "usage: chipsec_util.py [options] <command>\n")
    _patch_run(lambda *a, **k: _R(0, out=out))
    assert flash.available() is True


def test_available_rc_sifirdisi_ama_afis_varsa_basari():
    out = "usage: chipsec_util.py [options] <command>\n"
    _patch_run(lambda *a, **k: _R(2, out=out))
    assert flash.available() is True


# ---- _resolve_module() ----
def _patch_resolve(stdout):
    flash.subprocess.run = lambda *a, **k: _R(0, out=stdout)
    flash.reset_cmd_cache()


def test_resolve_top_level():
    _patch_resolve("ETA112MOD=chipsec_util\n")
    assert flash._resolve_module("py") == "chipsec_util"


def test_resolve_paket_ici():
    _patch_resolve("ETA112MOD=chipsec.chipsec_util\n")
    assert flash._resolve_module("py") == "chipsec.chipsec_util"


def test_resolve_bulunamazsa_fallback():
    _patch_resolve("ETA112MOD=\n")
    assert flash._resolve_module("py") == "chipsec_util"


def test_cmd_paket_ici_modulu_kullanir():
    # Çözüm paket içi modülü bulursa komut '-m chipsec.chipsec_util' olmalı.
    os.environ.pop("ETA112_CHIPSEC", None)
    flash.subprocess.run = lambda *a, **k: _R(0, out="ETA112MOD=chipsec.chipsec_util\n")
    flash.reset_cmd_cache()
    cmd = flash._chipsec_cmd()
    assert cmd[-2:] == ["-m", "chipsec.chipsec_util"], cmd


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
