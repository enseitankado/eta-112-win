# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Çıkışta geliştiriciye geri bildirim: Özgür Koca (ozgurkoca.com).

Ana menüden çıkarken kullanıcıya geri bildirim göndermek isteyip istemediği sorulur;
isterse yazdığı mesaj ntfy.sh üzerinden 'eta-112' konusuna gönderilir. Yalnız Python
standart kütüphanesini (urllib) kullanır — ek paket gerekmez.
"""

import sys
import urllib.request

from . import ui
from .ui import D, G, Y, OK, WARN

NTFY_TOPIC = "eta-112"

# Çıkışta gösterilen, geliştiriciyi motive edici mesaj. Son satırla e/h sorusu
# arasına bir boş satır konur (aşağıda exit_feedback).
_MOTIVASYON = [
    "Bu araç meşakkatli bir emeğin ürünüdür: Faz 1, Faz 2 Intel ve Faz 2 AMD",
    "tahtalarında defalarca donanım EEPROM sökülüp lehimlendi ve uzun bir",
    "tersine mühendislik çalışması yürütüldü. Küçük bir teşekkür, tavsiye ya",
    "da uyarı bile geliştiriciyi motive eder.",
]


def send_ntfy(message, topic=NTFY_TOPIC, timeout=15):
    """Mesajı ntfy.sh/<topic>'e POST eder. Döner (ok: bool, bilgi: str)."""
    url = "https://ntfy.sh/" + topic
    req = urllib.request.Request(
        url, data=message.encode("utf-8"), method="POST",
        headers={
            "Title": "eta-112-win geri bildirim",
            "Tags": "eta-112,windows,speech_balloon",
            "User-Agent": "eta-112-win",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", None) or r.getcode()
            return (200 <= int(code) < 300), "HTTP %s" % code
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _board_context():
    """Geliştiriciye bağlam: kart/BIOS (kişisel veri değil). Alınamazsa boş."""
    try:
        from .model import dmi
        d = dmi()
        parts = [d.get("board_mfr") or "", d.get("board") or "", d.get("bios_version") or ""]
        s = " ".join(p for p in parts if p).strip()
        return s
    except Exception:  # noqa: BLE001
        return ""


def exit_feedback():
    """Ana menüden çıkarken: geri bildirim iste ve (istenirse) ntfy'ye gönder.
    Yalnız etkileşimli (tty) oturumda sorar; otomasyon/EOF durumunda sessizce geçer."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return
    except Exception:  # noqa: BLE001
        return
    try:
        print()
        for _ln in _MOTIVASYON:
            print(D("  " + _ln))
        print()   # motive edici metnin son satırı ile e/h sorusu arasında boş satır
        if not ui.confirm_eh(
                "Geliştirici Özgür Koca'ya (ozgurkoca.com) bir mesaj bırakmak ister misiniz?",
                default_no=True):
            return
        print(D("  Mesajınız (tek satır). Boş bırakıp Enter'a basarsanız vazgeçilir."))
        try:
            msg = ui.ask("  > ").strip()
        except EOFError:
            return
        if not msg:
            print(D("  Geri bildirim gönderilmedi."))
            return
        ctx = _board_context()
        full = msg if not ctx else (msg + "\n\n[cihaz: " + ctx + "]")
        ok, info = send_ntfy(full)
        if ok:
            print(f"  {OK} {G('Geri bildiriminiz gönderildi — teşekkürler!')}")
        else:
            print(f"  {WARN} {Y('Gönderilemedi (' + info + '). İnternet bağlantınızı kontrol edin.')}")
    except KeyboardInterrupt:
        return
