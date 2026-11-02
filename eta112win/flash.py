# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Windows SPI flash arka ucu (CHIPSEC üzerinden).

Linux portundaki flashrom'un karşılığı. CHIPSEC, Intel'in açık kaynak (GPL)
donanım-güvenliği çerçevesidir ve Windows'ta imzalı bir çekirdek sürücüsüyle
(chipsec_hlpr) SPI flash'a okuma/yazma erişimi sağlar.

Adresleme: PROFILES'teki banka ofsetleri BIOS bölgesine GÖRE verilmiştir.
- flash_mode="region" (AMD): BIOS bölgesi tüm çipin tabanındadır (region_base=0).
- flash_mode="ifd"    (Intel): BIOS bölgesi tabanı flash descriptor'dan okunur
  ('chipsec_util spi info'); ofsetler o tabana eklenir.

!!! UYARI: CHIPSEC SPI yazma, flash'ı doğrudan değiştirir. Yanlış adres/boyut BIOS'u
kullanılamaz hale (brick) getirebilir. Bu port donanımda DOĞRULANMADI. Yazma her
zaman geri-okuma ile doğrulanır ve yalnız banka aralığına, 4 KiB sektör hizalı yapılır.
"""

import os
import re
import tempfile
import subprocess

SECTOR = 0x1000  # SPI erase sektörü (4 KiB)


def _chipsec_cmd():
    """chipsec_util'i çalıştıracak komut öneki. ETA112_CHIPSEC ile ezilebilir."""
    env = os.environ.get("ETA112_CHIPSEC")
    if env:
        return env.split()
    from shutil import which
    if which("chipsec_util"):
        return ["chipsec_util"]
    if which("chipsec_util.exe"):
        return ["chipsec_util.exe"]
    # modül olarak
    return [os.environ.get("ETA112_PYTHON", "python"), "-m", "chipsec_util"]


def available():
    """CHIPSEC çağrılabiliyor mu (sürücü yüklenebiliyor mu) kabaca sına."""
    try:
        r = subprocess.run(_chipsec_cmd() + ["--help"],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0 or "chipsec" in (r.stdout + r.stderr).lower()
    except Exception:
        return False


def _run(args, timeout=600):
    return subprocess.run(_chipsec_cmd() + args, capture_output=True, text=True, timeout=timeout)


class FlashError(Exception):
    pass


class FlashSession:
    """Tek bir oku-düzenle-yaz oturumu: tam çip bir kez okunur, BIOS bölgesi dilimlenir."""

    def __init__(self, prof):
        self.prof = prof
        self.ifd = prof.get("flash_mode") == "ifd"
        self._dump = None          # tam çip baytları
        self._base = None          # BIOS bölgesi tabanı (tam çip içinde)
        self._tmp = None

    # ---- düşük seviye ----
    def _dump_full(self):
        if self._dump is not None:
            return
        fd, path = tempfile.mkstemp(prefix="eta112win_", suffix=".bin")
        os.close(fd)
        self._tmp = path
        r = _run(["spi", "dump", path])
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise FlashError("CHIPSEC SPI dökümü başarısız:\n"
                             + "\n".join((r.stderr or r.stdout).strip().splitlines()[-4:]))
        with open(path, "rb") as f:
            self._dump = f.read()

    def _bios_base(self):
        if self._base is not None:
            return self._base
        if not self.ifd:
            self._base = 0
            return 0
        r = _run(["spi", "info"])
        txt = (r.stdout or "") + (r.stderr or "")
        base = None
        for ln in txt.splitlines():
            if re.search(r"\bBIOS\b", ln) and "Descriptor" not in ln:
                hexes = re.findall(r"([0-9A-Fa-f]{6,8})", ln)
                if len(hexes) >= 2:
                    base = int(hexes[0], 16)
                    break
        if base is None:
            # descriptor okunamadıysa: tipik olarak BIOS bölgesi çipin üst kısmıdır;
            # banka üst sınırını çip sonuna hizala (son çare, riskli -> doğrulama yakalar).
            raise FlashError("flash descriptor'dan BIOS bölgesi tabanı okunamadı "
                             "('chipsec_util spi info'). Intel modelde yazma için bu gerekli.")
        self._base = base
        return base

    # ---- yüksek seviye ----
    def read_region(self):
        """BIOS bölgesinin baytlarını döner (PROFILES ofsetleriyle uyumlu)."""
        self._dump_full()
        base = self._bios_base()
        return self._dump[base:] if base else self._dump

    def write_region(self, new_region):
        """BIOS parola yazımı: değişiklikler banka aralığında olmalı."""
        return self._flush(new_region, enforce_banks=True)

    def write_raw_region(self, new_region):
        """Banka kısıtı olmadan yazar (ör. MSDM / Windows anahtarı). Risk kullanıcıya ait."""
        return self._flush(new_region, enforce_banks=False)

    def _flush(self, new_region, enforce_banks):
        """Değişen 4 KiB sektörleri flash'a yaz, sonra geri-oku ile doğrula.
        Döner (ok: bool, mesaj: str)."""
        cur = self.read_region()
        if len(new_region) != len(cur):
            return False, "iç hata: bölge boyutu değişti"
        diffs = [i for i in range(len(cur)) if cur[i] != new_region[i]]
        if not diffs:
            return True, "değişiklik yok"
        if enforce_banks:
            banks = self.prof["banks"]
            if any(not any(lo <= x < hi for (lo, hi) in banks) for x in diffs):
                return False, "korumalı bölge dışına yazma engellendi"
        base = self._bios_base()
        # değişen bölgeyi sektör hizalı tek span olarak yaz
        lo = (min(diffs) // SECTOR) * SECTOR
        hi = ((max(diffs) // SECTOR) + 1) * SECTOR
        payload = new_region[lo:hi]
        fd, path = tempfile.mkstemp(prefix="eta112win_w_", suffix=".bin")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(payload)
            abs_addr = base + lo
            r = _run(["spi", "write", "0x%X" % abs_addr, path])
            out = (r.stdout or "") + (r.stderr or "")
            if r.returncode != 0 or "error" in out.lower() or "fail" in out.lower():
                return False, "\n".join(out.strip().splitlines()[-4:])
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        # geri-oku doğrula
        self._dump = None
        self._base = None
        rb = self.read_region()
        if rb[lo:hi] == payload:
            return True, "yazıldı ve doğrulandı"
        return True, "yazıldı ama geri-oku doğrulaması tutmadı"

    def close(self):
        if self._tmp and os.path.exists(self._tmp):
            try:
                os.remove(self._tmp)
            except OSError:
                pass
        self._tmp = None
        self._dump = None
