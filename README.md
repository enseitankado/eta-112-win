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
- **SPI flash okuma/yazma** için [CHIPSEC](https://github.com/chipsec/chipsec):
  `pip install chipsec`. CHIPSEC imzalı bir çekirdek sürücüsü yükler; yüklenebilmesi
  için **Secure Boot / HVCI (bellek bütünlüğü) kapalı** ya da test imzalama açık olmalı.
- **MAC değiştirme** için Realtek'in Windows PG aracı (ör. `PG8168` / `RtNicpg`).

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
python eta-112-win.py bios read --dump dump.bin         :: bir ROM dökümünden oku
python eta-112-win.py bios set --yonetici PAROLA         :: yönetici parolası ayarla
python eta-112-win.py bios set --kullanici PAROLA        :: kullanıcı parolası ayarla
python eta-112-win.py bios clear all                    :: tüm BIOS parolalarını sil
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

---

## Geliştirici ve lisans

- Geliştirici: **Özgür Koca** — [ozgurkoca.com](https://ozgurkoca.com)
- Lisans: **GPL-3.0-or-later** (üst proje eta-112 ile aynı) — özgür yazılım.
- Üst proje: <https://github.com/enseitankado/eta-112>
