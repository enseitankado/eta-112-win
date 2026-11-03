# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Menü ESC davranışı: ana menüde 2× Esc çıkış, alt menüde 1× Esc üst menüye dönüş.

Menü etkileşimlidir (msvcrt); _read_key bir tuş dizisiyle taklit edilir, _draw
susturulur. Donanım/tty gerekmez.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eta112win import ui  # noqa: E402


class _NoMoreKeys(Exception):
    """Tuş dizisi bittiğinde: menü döngüsü hâlâ tuş bekliyor demektir (çıkmadı)."""


def _feed(keys):
    it = iter(keys)

    def _rk():
        try:
            return next(it)
        except StopIteration:
            raise _NoMoreKeys()
    return _rk


def _patch(keys):
    ui._read_key = _feed(keys)
    ui._draw = lambda *a, **k: None
    ui._interactive = lambda: True
    ui.ask = lambda *a, **k: ""


ITEMS = [("A", "", lambda: None), ("Çıkış", "", None)]


def test_submenu_tek_esc_geri():
    _patch(["esc"])
    assert ui.menu_loop("alt", ITEMS, ana=False) == 0


def test_ana_iki_esc_cikis():
    _patch(["esc", "esc"])
    assert ui.menu_loop("ana", ITEMS, ana=True) == 0


def test_ana_tek_esc_cikmaz():
    _patch(["esc"])  # yalnız 1 Esc; çıkmamalı -> 2. tuşu beklerken dizi biter
    try:
        ui.menu_loop("ana", ITEMS, ana=True)
        assert False, "ana menü tek Esc ile çıktı (hata)"
    except _NoMoreKeys:
        pass


def test_ana_esc_sayaci_sifirlanir():
    # esc, down (sayaç sıfırlanır), esc -> toplam ardışık 1 Esc -> çıkmamalı
    _patch(["esc", "down", "esc"])
    try:
        ui.menu_loop("ana", ITEMS, ana=True)
        assert False, "sayaç sıfırlanmadı; beklenmedik çıkış"
    except _NoMoreKeys:
        pass


def test_ana_down_sonra_iki_esc_cikis():
    _patch(["down", "esc", "esc"])
    assert ui.menu_loop("ana", ITEMS, ana=True) == 0


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
