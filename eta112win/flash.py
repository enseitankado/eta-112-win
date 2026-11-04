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
import sys
import tempfile
import subprocess

SECTOR = 0x1000  # SPI erase sektörü (4 KiB)


_CMD_CACHE = None


def _resolve_module(py):
    """chipsec_util'i 'python -m' ile çalıştırmak için IMPORT EDİLEBİLİR modül adını
    bul. chipsec sürümüne göre bu ya top-level 'chipsec_util' (1.13.x wheel/sdist)
    ya da paket içi 'chipsec.chipsec_util' (bazı yeni sürümler) olabilir. Sabit
    'chipsec_util' kullanmak, modülü paket içine taşıyan bir sürüm kurulduğunda
    'No module named chipsec_util' hatasına yol açıyordu. Hedef yorumlayıcıda
    find_spec ile gerçekten var olanı seçeriz (top-level önce: chipsec'i import
    etmeden sınanır)."""
    probe = (
        "import importlib.util as u\n"
        "name=''\n"
        "for m in ('chipsec_util','chipsec.chipsec_util'):\n"
        "    try:\n"
        "        if u.find_spec(m): name=m; break\n"
        "    except Exception: pass\n"
        "print('ETA112MOD='+name)\n")
    try:
        r = subprocess.run([py, "-I", "-c", probe],
                           capture_output=True, text=True, timeout=90)
        for ln in (r.stdout or "").splitlines():
            if ln.startswith("ETA112MOD="):
                name = ln[len("ETA112MOD="):].strip()
                if name:
                    return name
    except Exception:
        pass
    return "chipsec_util"


def _chipsec_cmd():
    """chipsec_util'i çalıştıracak komut öneki. ETA112_CHIPSEC ile ezilebilir.

    Varsayılan olarak ARACI ÇALIŞTIRAN yorumlayıcıyı (sys.executable) kullanır ve
    o yorumlayıcıda gerçekten var olan modül adını (_resolve_module) seçer. Böylece
    chipsec hangi yerleşimle kurulmuş olursa olsun ('chipsec_util' ya da
    'chipsec.chipsec_util') doğru '-m' hedefi bulunur. Çözüm önbelleğe alınır."""
    global _CMD_CACHE
    env = os.environ.get("ETA112_CHIPSEC")
    if env:
        return env.split()
    if _CMD_CACHE is not None:
        return list(_CMD_CACHE)
    py = os.environ.get("ETA112_PYTHON") or sys.executable or "python"
    _CMD_CACHE = [py, "-m", _resolve_module(py)]
    return list(_CMD_CACHE)


def reset_cmd_cache():
    """chipsec kurulumu değiştikten sonra modül çözümünü yeniden yaptır."""
    global _CMD_CACHE
    _CMD_CACHE = None


def available():
    """chipsec_util ÇAĞRILABİLİYOR mu (paket + giriş noktası yerinde mi) kabaca sına.
    DİKKAT: bu, çekirdek sürücüsünün yüklendiği anlamına gelmez — onun için
    spi_probe() kullanın."""
    try:
        r = subprocess.run(_chipsec_cmd() + ["--help"],
                           capture_output=True, text=True, timeout=90)
    except Exception:
        return False
    out = (r.stdout or "") + (r.stderr or "")
    low = out.lower()
    # '-m chipsec_util --help' başarıyla çalışınca çıkış kodu 0'dır. Modül
    # bulunamazsa ('No module named chipsec_util') Python çıkış kodu != 0 verir ve
    # afiş/usage HİÇ görünmez. Bu yüzden önce çıkış koduna bakarız.
    # (Eski 'chipsec' alt-dizisi testi, hata metni 'chipsec_util' içerdiği için
    # bozuk durumu yanlışlıkla 'başarılı' sayıyordu — kaldırıldı. CHIPSEC afişinde
    # 'No module named chipsec.library.tpm' gibi ZARARSIZ satırlar da olabilir; bu
    # yüzden 'no module named' metnine değil, çıkış kodu + afiş'e bakarız.)
    if r.returncode == 0:
        return True
    return ("usage: chipsec_util" in low or "[chipsec] version" in low
            or "util command to run" in low)


def _run(args, timeout=600):
    return subprocess.run(_chipsec_cmd() + args, capture_output=True, text=True, timeout=timeout)


def _parse_bios_region(txt):
    """CHIPSEC 'spi info' çıktısından BIOS bölgesinin (base, limit) ikilisini çıkarır.
    Tablo biçimi sürüme göre 2 ya da 3 sütun olabilir:
        '1 BIOS (FREG1) | 7FFF0500 | 00500000 | 00FFFFFF'  -> base/limit SON iki grup
        'BIOS            00500000   00FFFFFF'                -> base/limit iki grup
    Bu yüzden satırdaki SON iki 8-haneli hex, base ve limit olarak alınır
    (eski sürüm yanlışlıkla FREG register değerini taban sanıyordu)."""
    for ln in txt.splitlines():
        if not re.search(r"\bBIOS\b", ln) or "Descriptor" in ln:
            continue
        hexes = re.findall(r"[0-9A-Fa-f]{8}", ln)
        if len(hexes) >= 2:
            base = int(hexes[-2], 16)
            limit = int(hexes[-1], 16)
            if limit >= base and limit > 0:
                return base, limit
    return None


def _is_launch_failure(txt):
    """chipsec_util'in HİÇ çalışmadığını (yanlış '-m' hedefi / bozuk kurulum /
    import çöküşü) gösterir — bunun SÜRÜCÜYLE İLGİSİ YOKTUR. CHIPSEC afişi çıktıysa
    modül yüklenmiş demektir; afiş YOKKEN 'No module named' görmek, chipsec_util'in
    hiç başlamadığını söyler (ör. eski sabit '-m chipsec_util' hatası)."""
    low = txt.lower()
    banner = "[chipsec]" in low or "chipsec_util.py" in low or "util command to run" in low
    if banner:
        return False
    return ("no module named" in low or "modulenotfounderror" in low
            or "can't open file" in low or "no module" in low)


def spi_probe():
    """Çekirdek sürücüsünü yükleyip 'spi info' ile flash descriptor okumayı dener.
    Salt-okunur bir sorgudur (flash'a yazmaz). Döner (ok: bool, detay: str).
    DİKKAT: 'sürücü yüklenemedi' ile 'chipsec_util hiç çalışmadı (kurulum bozuk)'
    ayrı raporlanır; ikincisi için sürücü derlemeye yönlendirmek YANLIŞ olur."""
    try:
        r = _run(["spi", "info"], timeout=150)
    except Exception as e:
        return False, "chipsec çağrılamadı: %s" % e
    txt = (r.stdout or "") + (r.stderr or "")
    reg = _parse_bios_region(txt)
    if reg is not None:
        return True, "BIOS bölgesi 0x%X-0x%X" % (reg[0], reg[1])
    if r.returncode == 0 and "flash region" in txt.lower():
        return True, "descriptor okundu"
    tail = "; ".join([l.strip() for l in txt.strip().splitlines() if l.strip()][-2:])
    if _is_launch_failure(txt):
        return False, ("CHIPSEC_KURULUM_BOZUK: chipsec_util çalıştırılamadı "
                       "(sürücü sorunu DEĞİL): " + (tail or "modül bulunamadı"))
    low = txt.lower()
    if ("--pch" in low or "correct configuration is not loaded" in low
            or "unsupported platform" in low or "could not detect" in low
            or "unknown platform" in low):
        # chipsec yonga setini algılayamadı (ör. eski AMD FCH — chipsec 1.13'te config yok).
        # Bu bir SÜRÜCÜ sorunu DEĞİLDİR; o modelde canlı SPI chipsec ile mümkün değil.
        return False, ("PLATFORM_DESTEKLENMIYOR: chipsec bu yonga setini otomatik "
                       "algılayamadı (ör. VESTEL 14MB37C1 / eski AMD FCH). Bu modelde "
                       "canlı SPI chipsec ile DESTEKLENMİYOR. Çevrimdışı '--dump' ile "
                       "okuma/dry-run kullanın ya da AMD için Linux eta-112 (flashrom).")
    return False, (tail or "SPI descriptor okunamadı (sürücü yüklenemedi?)")


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
        reg = _parse_bios_region(txt)
        base = reg[0] if reg else None
        if base is None:
            # descriptor okunamadıysa: tipik olarak BIOS bölgesi çipin üst kısmıdır;
            # banka üst sınırını çip sonuna hizala (son çare, riskli -> doğrulama yakalar).
            raise FlashError("flash descriptor'dan BIOS bölgesi tabanı okunamadı "
                             "('chipsec_util spi info'). Intel modelde yazma için bu gerekli.")
        self._base = base
        return base

    # ---- yüksek seviye ----
    def read_region(self):
        """TAM SPI çipini (MUTLAK ofsetlerle) döner.

        PROFILES'teki banka/slot ofsetleri üst proje eta-112 (Linux/flashrom) ile
        BİREBİR aynıdır ve TAM ÇİP mutlak ofsetleridir (ör. 14MB57 bankaları
        0x400000+). Bu yüzden bölgeyi BIOS tabanından KIRPMAYIZ: kırpmak tüm
        ofsetleri 'base' kadar kaydırır, hiçbir giriş bankalara düşmez ve
        resolve_current None döner — geçerli parola 'güncel' yerine 'önceki'
        olarak görünür. (Yazarken mutlak ofsete yazılır; bkz. _flush.)"""
        self._dump_full()
        return self._dump

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
        # değişen bölgeyi sektör hizalı tek span olarak yaz. read_region TAM çipi
        # döndürdüğü için lo/hi zaten MUTLAK flash ofsetleridir (base eklenmez).
        lo = (min(diffs) // SECTOR) * SECTOR
        hi = ((max(diffs) // SECTOR) + 1) * SECTOR
        payload = new_region[lo:hi]
        fd, path = tempfile.mkstemp(prefix="eta112win_w_", suffix=".bin")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(payload)
            abs_addr = lo
            # Yazma öncesi BIOS Write Enable (BIOSWE=1). Gözlendi: BIOSWE=0 iken chipsec
            # erase/write "tamamlandı" dese de flash değişmiyor. chipsec 'spi disable-wp'
            # BIOSWE'yi açar (Linux'ta flashrom bunu kendi halleder). BLE=0 olduğundan
            # ayar kalıcıdır; reboot'ta sıfırlanır (geri dönüşlü).
            _run(["spi", "disable-wp"])
            # SPI flash'a PROGRAMLAMADAN ÖNCE sektörleri SİL. chipsec 'spi write' erase
            # YAPMAZ; silinmemiş (0xFF olmayan) sektöre programlama bitleri 1->0 ancak
            # çevirebildiği için yazma etkisiz/bozuk olur (Linux'ta flashrom erase+write
            # yapar). payload zaten tam sektör(ler) içeriği olduğundan erase güvenli:
            # yalnız hedeflenen slot değişir, sektörün gerisi aynen geri yazılır.
            erase_out = ""
            for sa in range(lo, hi, SECTOR):
                er = _run(["spi", "erase", "0x%X" % sa])
                erase_out += (er.stdout or "") + (er.stderr or "")
            r = _run(["spi", "write", "0x%X" % abs_addr, path])
            out = erase_out + (r.stdout or "") + (r.stderr or "")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        # Başarıyı GERİ-OKU ile doğrula. DİKKAT: chipsec, EfiCompressor'suz kurulumda
        # her çağrıda zararsız bir "ERROR: Failed to import compression module" banner'ı
        # yazar; bu yüzden çıktıdaki 'error'/'fail' metnine BAKMAYIZ (yanlış pozitif) —
        # tek gerçek ölçüt flash'ın gerçekten değişmesidir.
        self._dump = None
        self._base = None
        try:
            rb = self.read_region()
        except FlashError as e:
            return False, "yazma sonrası geri-okuma başarısız: %s" % e
        if rb[lo:hi] == payload:
            return True, "yazıldı ve doğrulandı"
        # Komut 'tamamlandı' dese bile flash değişmediyse: donanım yazmayı reddetmiş.
        completed = "completed" in out.lower()
        if completed:
            return False, ("yazma donanımda ETKİLİ OLMADI: chipsec tamamlandı ama flash "
                           "değişmedi. BIOS bölgesi büyük olasılıkla donanımda yazma "
                           "korumalı (flash chip SR blok-koruma ya da descriptor bölge "
                           "erişimi). Secure Boot kapalı + PR0-4/BIOSWE temiz olsa da "
                           "bazı kartlar OS altında SPI yazmayı kabul etmez.")
        tail = "\n".join([l for l in out.strip().splitlines()
                          if "compression module" not in l.lower()][-4:])
        return False, "yazma başarısız:\n" + tail

    def close(self):
        if self._tmp and os.path.exists(self._tmp):
            try:
                os.remove(self._tmp)
            except OSError:
                pass
        self._tmp = None
        self._dump = None
