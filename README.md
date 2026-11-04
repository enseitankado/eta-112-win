# eta-112-win

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-informational)
![Python](https://img.shields.io/badge/python-3-blue)

Pardus ETAP akıllı tahtalar için [eta-112](https://github.com/enseitankado/eta-112)
bakım aracının **Windows portu**: **BIOS parolası**, **MAC adresi** ve **Windows ürün
anahtarı** gibi firmware değerlerini okur/yazar. Yalnız [desteklenen
modellerde](#desteklenen-tahtalar) çalışır.

> ⚠️ Yazma işlemleri SPI flash'ı doğrudan değiştirir; yanlış yazma BIOS'u brick
> edebilir. Önce yedek alın. Ayrıntı: **[MANUAL.md](MANUAL.md)**.

## Hızlı başlangıç

**Yönetici** bir PowerShell açıp yapıştırın (Python'u kurar, depoyu indirir, menüyü açar):

```powershell
irm https://raw.githubusercontent.com/enseitankado/eta-112-win/main/baslat.ps1 | iex
```

Elle çalıştırma:

```bat
python eta-112-win.py          :: menü
python eta-112-win.py bios read   :: BIOS parolasını oku
python eta-112-win.py wkey read   :: Windows anahtarını oku
```

Menüde: ok tuşları + Enter, **Esc** geri; **ana menüde iki kez Esc** çıkış.

Canlı BIOS okuma/yazma için CHIPSEC + çekirdek sürücüsü gerekir; tek komutla kurulur:

```powershell
powershell -ExecutionPolicy Bypass -File tools\surucu-kur.ps1
```

Tüm komutlar, kurulum ayrıntıları, sürücü ve sorun giderme için **[MANUAL.md](MANUAL.md)**.

## Desteklenen tahtalar

| Model | Anakart | BIOS | Windows'ta |
|---|---|---|---|
| Faz 1 Vestel Intel | VESTEL 14MB24A | AMI Aptio 4.6.5 | ⚠️ donanımda sınanmadı |
| Faz 2 Vestel AMD | VESTEL 14MB37C1 | AMI Aptio L0.30 | ✅ okuma doğrulandı |
| Faz 2 Vestel Intel | VESTEL 14MB57 | AMI Aptio 4.6.5 | ✅ okuma + yazma doğrulandı |

> **Windows portu Faz 2 (Intel + AMD) tahtalar için geliştirildi ve gerçek donanımda
> doğrulandı.** Faz 1 Intel (14MB24A), doğrulanmış 14MB57 ile aynı Intel mekanizmasını
> kullanır (çalışması beklenir) ama Windows donanımında sınanmadı; araç bu modelde
> çalışırken uyarı verir.

## Lisans

Geliştirici **Özgür Koca** ([ozgurkoca.com](https://ozgurkoca.com)) ·
**GPL-3.0-or-later** · Üst proje: <https://github.com/enseitankado/eta-112>
