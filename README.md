# eta-112-win

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-informational)
![Python](https://img.shields.io/badge/python-3-blue)

Pardus ETAP akıllı tahtalar için [eta-112](https://github.com/enseitankado/eta-112)
bakım aracının **Windows portu**. Firmware/EEPROM işlevlerini — BIOS parolası, MAC
adresi ve Windows ürün anahtarı — Windows üzerinde çalışan sistemden uygular.

BIOS parolası, MAC adresi ve Windows ürün anahtarı firmware/donanım seviyesindedir —
disk silinse de kalıcıdır ve yalnızca **desteklenen modellerde** çalışır.

> ⚠️ **Önemli:** Yazma işlemleri (`bios set/clear`, `wkey set`) SPI flash'ı doğrudan
> değiştirir ve **bu port henüz gerçek donanımda doğrulanmamıştır**. Çözümleme/kodlama
> mantığı üst projeden (Linux'ta uçtan uca doğrulanmış) birebir taşınmıştır; Windows'a
> özgü olan tek şey donanım erişim katmanıdır (CHIPSEC + Win32 API). Yanlış yazma BIOS'u
> kullanılamaz (brick) hale getirebilir. Önce bir tezgah tahtasında sınayın.

---

## Çalıştırma

Kurulum gerektirmez. **Yönetici** bir PowerShell açıp aşağıdaki tek satırı yapıştırın;
betik yönetici değilse kendini yükseltir, Python yoksa kurar, depoyu indirip menüyü açar:

```powershell
irm https://raw.githubusercontent.com/enseitankado/eta-112-win/main/baslat.ps1 | iex
```

(eta-112'nin `curl -fsSL .../baslat.sh | sudo bash` yönteminin Windows karşılığıdır.)

Depoyu elle indirdiyseniz doğrudan da çalıştırabilirsiniz:

```bat
python eta-112-win.py
```

Her iki yolda da araç **başlangıçta ön kurulumu katmanlı denetler** (Python, yönetici,
CHIPSEC paketi, **SPI çekirdek sürücüsü**, Secure Boot) ve eksik olan CHIPSEC paketini —
yönetici haklarıyla — **derleyici gerektirmeden otomatik kurmayı önerir** (ayrıntı için
aşağıdaki [CHIPSEC ve sürücü](#chipsec-ve-sürücü-spi-erişimi) bölümüne bakın). Denetimi
tek başına çalıştırmak için:

```bat
python eta-112-win.py kontrol
```

Açılan menüden ok tuşlarıyla gezinip Enter ile seçim yapılır (1–9 doğrudan, Esc geri).

---

## Neden ayrı bir port?

Orijinal eta-112 Linux (canlı USB / çalışan sistem) içindir ve donanıma şu yollarla
erişir: `flashrom` (SPI flash), `rtnicpg`+`pgdrv.ko` (Realtek eFuse), `efivarfs`
(`/sys/firmware/efi/...`) ve `/sys/firmware/acpi/tables/MSDM`. Bunların hiçbiri
Windows'ta yoktur; her biri Windows karşılığıyla değiştirilmiştir:

| İşlev | Linux (eta-112) | Windows (eta-112-win) | Durum |
|---|---|---|---|
| Windows anahtarı **oku** | `/sys/.../MSDM` | `GetSystemFirmwareTable('ACPI','MSDM')` | ✅ sürücüsüz çalışır |
| MAC **oku / doğrula** | sysfs + kural | `GetAdaptersInfo` + kural | ✅ sürücüsüz çalışır |
| Model saptama | `dmidecode` | `GetSystemFirmwareTable('RSMB')` SMBIOS | ✅ sürücüsüz çalışır |
| BIOS parolası **oku** | `flashrom` | CHIPSEC `spi dump` | ⚠️ CHIPSEC gerekir; donanımda doğrulanmadı |
| BIOS parolası **yaz/sil** | `flashrom` | CHIPSEC `spi write` | ⚠️ CHIPSEC gerekir; donanımda doğrulanmadı |
| Windows anahtarı **değiştir** | `flashrom` | CHIPSEC `spi write` | ⚠️ CHIPSEC gerekir; donanımda doğrulanmadı |
| MAC **değiştir** (eFuse) | `rtnicpg`+`pgdrv.ko` | Realtek Windows PG aracı | ⛔ otomatik değil (vendor aracı gerekir) |

Platform-bağımsız mantık (profil tablosu, XOR-keystream çöz/kodla, Türkçe-Q eşlemesi,
AMI Aptio NVAR tarama, MSDM ayrıştırma, MAC kural denetimi) üst projeyle **birebir**
aynıdır (`eta112win/codec.py`, `eta112win/profiles.py`).

### Porta alınmayanlar
- **Dokunmatik sürücü** (Linux çekirdek modülü/DKMS) — Windows'ta karşılığı yok.
- **Kullanıcı hesabı parolası sıfırlama** — eta-112'de Linux kurulumunun diskini
  bağlayıp `/etc/shadow` düzenler; Windows yerel hesap sıfırlama bambaşka bir iştir ve
  bu aracın kapsamı dışındadır (karıştırmamak için bilinçli olarak dahil edilmedi).

---

## Gereksinimler

- **Windows** (çalışan sistem) ve **Yönetici (Administrator)** hakları.
- **Python 3**.
- Yalnız **okuma** için (Windows anahtarı, MAC): ek bir şey gerekmez — araç yalnız
  standart kütüphane + Windows DLL'lerini (ctypes) kullanır.
- **SPI flash okuma/yazma** için [CHIPSEC](https://github.com/chipsec/chipsec) +
  bir **çekirdek sürücüsü**. Bu iki ayrı şeydir; aşağıdaki bölüme bakın. Her durumda
  sürücünün yüklenebilmesi için **Secure Boot / HVCI (bellek bütünlüğü) kapalı** ya da
  test imzalama açık olmalı — araç Secure Boot açıksa uyarır (bu tahtalarda kapalıdır).
- **MAC değiştirme** için Realtek'in Windows PG aracı (ör. `PG8168` / `RtNicpg`).

### CHIPSEC ve sürücü (SPI erişimi)

Windows'ta canlı SPI erişimi **iki katman** ister; aracın `kontrol` komutu ikisini
ayrı ayrı denetler:

1. **CHIPSEC Python paketi.** PyPI'deki `pip install chipsec` iki nedenle temiz bir
   tahtada sorun çıkarır: (a) kaynaktan `EfiCompressor` adlı bir C uzantısı derler ve
   *Microsoft Visual C++ Build Tools* ister; (b) paket **önceden derlenmiş çekirdek
   sürücüsü içermez**. (a) için araç chipsec'i **EfiCompressor olmadan** kurar
   (uzantı yalnız UEFI sıkıştırma modülleri içindir, SPI için gereksizdir) — böylece
   **derleyici gerekmez**. Bunu `python eta-112-win.py kontrol` yapar.

2. **Çekirdek sürücüsü** (asıl kapı). CHIPSEC paketi kurulu olsa da SPI, sürücü
   yüklenmeden çalışmaz. İki yol vardır:
   - **A) RWEverything `RwDrv.sys` (önerilir — derleme/.NET gerekmez):**
     [rweverything.com](https://rweverything.com)'dan aracı indirip `RwDrv.sys`'i
     chipsec'in `rwe` yardımcısının klasörüne koyun
     (`…\site-packages\chipsec\helper\rwe\windows_amd64\RwDrv.sys`) ve aracı o
     yardımcıya yönlendirin:
     `setx ETA112_CHIPSEC "python -m chipsec_util -i -n --helper rwe"`.
     RwDrv.sys WHQL-imzalıdır; Secure Boot kapalıyken test imzalama olmadan yüklenir.
   - **B) chipsec'in kendi sürücüsünü derleyin:** Visual Studio + WDK + **.NET
     Framework (MSBuild)** ile chipsec kaynağından sürücüyü derleyip imzalayın
     (chipsec-manual.pdf). .NET Framework **yalnız bu yol için** gereklidir.

Sürücü olmadan da **`bios read --dump` ile çevrimdışı okuma** ve **`bios set/clear …
--out` ile çevrimdışı dry-run yazma** tam çalışır (aşağıya bakın).

---

## Desteklenen donanımlar

<!-- eta-112 ile aynı profiller -->
| Faz / Model | Anakart | İşlemci | BIOS |
|---|---|---|---|
| Faz 1 Vestel Intel (Siyah) | VESTEL 14MB24A | Intel Core i3-2310M | AMI Aptio 4.6.5 |
| Faz 2 Vestel AMD (Gri) | VESTEL 14MB37C1 | AMD A10-5750M | AMI Aptio L0.30 |
| Faz 2 Vestel Intel (Gri) | VESTEL 14MB57 | Intel Core i3-4000M | AMI Aptio 4.6.5 |

---

## Kullanım

Yönetici bir CMD/PowerShell açın:

```bat
python eta-112-win.py                  :: etkileşimli menü
```

Komut satırı:

```bat
python eta-112-win.py bios info                         :: model / destek
python eta-112-win.py bios read                         :: parolaları oku (CHIPSEC)
python eta-112-win.py bios read --dump dump.bin         :: bir ROM dökümünden oku (sürücüsüz)
python eta-112-win.py bios set --yonetici PAROLA         :: yönetici parolası ayarla (canlı)
python eta-112-win.py bios set --kullanici PAROLA        :: kullanıcı parolası ayarla (canlı)
python eta-112-win.py bios clear all                    :: tüm BIOS parolalarını sil (canlı)

:: Çevrimdışı dry-run (donanıma DOKUNMAZ; --dump kaynağını düzenleyip --out'a yazar):
python eta-112-win.py bios set --yonetici PAROLA --dump dump.bin --out yeni.bin
python eta-112-win.py bios clear all --dump dump.bin --out temiz.bin
python eta-112-win.py bios calibrate yonetici PAROLA    :: bilinen parolayla keystream doğrula

python eta-112-win.py mac read                          :: MAC(ler) + Faz OUI durumu
python eta-112-win.py mac check 00:09:DF:12:34:56       :: yazmadan önce sına
python eta-112-win.py mac set  00:09:DF:12:34:56         :: (Windows'ta vendor aracı gerekir)

python eta-112-win.py wkey read                         :: Windows ürün anahtarını göster
python eta-112-win.py wkey set XXXXX-XXXXX-XXXXX-XXXXX-XXXXX
```

Her komuta `--json` eklenirse makine-okur (GUI/otomasyon) çıktı verir; sözleşme
orijinal eta-112 ile aynıdır. Her komutun `-h` yardımı vardır.

### Doğrulama ve güvenlik
- Her yazma işlemi **geri-oku ile doğrulanır**; ayrıca değişiklikler yalnız parola
  NVRAM bankalarına (veya MSDM için yalnız ilgili sektöre), 4 KiB sektör hizalı yapılır.
- Değişikliğin etkili olması için **yeniden başlatma** gerekir.
- `--dump` ile okuma donanıma dokunmaz; yeni bir modeli doğrularken `calibrate` kullanın.
- `--out` ile dry-run yazma da donanıma dokunmaz: parola oku/yaz mantığını brick riski
  olmadan geliştirmek/doğrulamak ve harici flashlama için düzenlenmiş ROM üretmek içindir.

### Geliştirme ve testler

Parola oku/yaz çözümleme mantığı, donanım gerektirmeyen bir regresyon testiyle
doğrulanır (sentetik bir AMI NVAR imajında oku → yaz → yeniden oku → temizle):

```bat
python tests\test_bios_roundtrip.py
```

---

## Geliştirici ve lisans

- Geliştirici: **Özgür Koca** — [ozgurkoca.com](https://ozgurkoca.com)
- Lisans: **GPL-3.0-or-later** (üst proje eta-112 ile aynı) — özgür yazılım.
- Üst proje: <https://github.com/enseitankado/eta-112>
