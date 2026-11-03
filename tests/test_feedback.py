# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Çıkış geri bildirim akışı: tty guard + evet->ntfy'ye gönder, hayır->gönderme.

send_ntfy ağ çağrısı taklit edilir (gerçek POST yapılmaz). tty, dummy akışlarla
simüle edilir.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eta112win import feedback, ui  # noqa: E402


class _Stream:
    def __init__(self, tty=True):
        self._tty = tty
    def isatty(self):
        return self._tty
    def write(self, *a, **k):
        return 0
    def flush(self):
        pass
    def readline(self):
        return "\n"


def _run(tty, say_yes, message):
    """exit_feedback'i izole çalıştırır; gönderilen mesajı (veya None) döner."""
    sent = []
    orig = (sys.stdin, sys.stdout, ui.confirm_eh, ui.ask, feedback.send_ntfy,
            feedback._board_context)
    sys.stdin = _Stream(tty)
    sys.stdout = _Stream(tty)
    ui.confirm_eh = lambda *a, **k: say_yes
    ui.ask = lambda *a, **k: message
    feedback.send_ntfy = lambda m, **k: (sent.append(m) or (True, "HTTP 200"))
    feedback._board_context = lambda: "VESTEL 14MB57 4.6.5"
    try:
        feedback.exit_feedback()
    finally:
        (sys.stdin, sys.stdout, ui.confirm_eh, ui.ask, feedback.send_ntfy,
         feedback._board_context) = orig
    return sent[0] if sent else None


def test_evet_gonderir():
    m = _run(tty=True, say_yes=True, message="harika bir arac")
    assert m is not None and "harika bir arac" in m


def test_evet_cihaz_baglami_eklenir():
    m = _run(tty=True, say_yes=True, message="selam")
    assert "VESTEL 14MB57" in m


def test_hayir_gondermez():
    assert _run(tty=True, say_yes=False, message="x") is None


def test_bos_mesaj_gondermez():
    assert _run(tty=True, say_yes=True, message="   ") is None


def test_tty_yoksa_sormaz_gondermez():
    assert _run(tty=False, say_yes=True, message="x") is None


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
