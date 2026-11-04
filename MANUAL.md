# eta-112-win — Kılavuz (MANUAL)

Bu belge, [eta-112-win](README.md) aracının ayrıntılı kullanım, kurulum ve teknik
bilgilerini içerir. Hızlı başlangıç için [README.md](README.md)'ye bakın.

---

## İçindekiler

- [Ne işe yarar](#ne-işe-yarar)
- [Neden ayrı bir port](#neden-ayrı-bir-port)
- [Desteklenen donanımlar](#desteklenen-donanımlar)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
- [CHIPSEC ve sürücü (SPI erişimi)](#chipsec-ve-sürücü-spi-erişimi)
- [Komut başvurusu](#komut-başvurusu)
- [Çevrimdışı mod: `--dump` ve `--out`](#çevrimdışı-mod---dump-ve---out)
- [Menü ve kısayollar](#menü-ve-kısayollar)
- [İşlem süreleri](#işlem-süreleri)
- [Doğrulama ve güvenlik](#doğrulama-ve-güvenlik)
- [Canlı yazma ve donanım notları](#canlı-yazma-ve-donanım-notları)
- [Geliştirme ve testler](#geliştirme-ve-testler)
- [Sorun giderme](#sorun-giderme)
- [Lisans](#lisans)

---

## Ne işe yarar

Pardus ETAP akıllı tahtalar için [eta-112](https://github.com/enseitankado/eta-112)
bakım aracının Windows portudur. Firmware/EEPROM işlevlerini — **BIOS parolası**,
**MAC adresi** ve **Windows ürün anahtarı** — Windows üzerinde çalışan sistemden
uygular. Bu değerler firmware/donanım seviyesindedir: disk silinse de kalıcıdır ve
yalnız **desteklenen modellerde** çalışır.

---

## Neden ayrı bir port

Orijinal eta-112 Linux (canlı USB / çalışan sistem) içindir ve donanıma şu yollarla
erişir: `flashrom` (SPI flash), `rtnicpg`+`pgdrv.ko` (Realtek eFuse), `efivarfs` ve
`/sys/firmware/acpi/tables/MSDM`. Bunların hiçbiri Windows'ta yoktur; her biri Windows
karşılığıyla değiştirilmiştir:

| İşlev | Linux (eta-112) | Windows (eta-112-win) | Durum |
|---|---|---|---|
| Windows anahtarı **oku** | `/sys/.../MSDM` | `GetSystemFirmwareTable('ACPI','MSDM')` | ✅ sürücüsüz |
| MAC **oku / doğrula** | sysfs + kural | `GetAdaptersInfo` + kural | ✅ sürücüsüz |
| Model saptama | `dmidecode` | `GetSystemFirmwareTable('RSMB')` SMBIOS | ✅ sürücüsüz |
| BIOS parolası **oku** | `flashrom` | Intel: CHIPSEC `spi dump` · AMD: bellek-haritalı ROM (`read_phys_mem`) | ✅ 14MB57 (Intel) ve 14MB37C1 (AMD) canlı doğrulandı |
| BIOS parolası **yaz/sil** | `flashrom` | CHIPSEC `disable-wp`+`erase`+`write` | ✅ sürücü ister; 14MB57'de canlı doğrulandı |
| Windows anahtarı **değiştir** | `flashrom` | CHIPSEC `spi write` | ⚠️ sürücü ister |
| MAC **değiştir** (eFuse) | `rtnicpg`+`pgdrv.ko` | Realtek Windows PG aracı | ⛔ otomatik değil (vendor aracı) |

Platform-bağımsız mantık (profil tablosu, XOR-keystream çöz/kodla, Türkçe-Q eşlemesi,
AMI Aptio NVAR tarama, MSDM ayrıştırma, MAC kural denetimi) üst projeyle **birebir**
aynıdır (`eta112win/codec.py`, `eta112win/profiles.py`). Windows'a özgü olan tek şey
donanım erişim katmanıdır (`eta112win/flash.py` → CHIPSEC + Win32 API).

### Porta alınmayanlar
- **Dokunmatik sürücü** (Linux çekirdek modülü/DKMS) — Windows'ta karşılığı yok.
- **Kullanıcı hesabı parolası sıfırlama** — eta-112'de Linux diskini bağlayıp
  `/etc/shadow` düzenler; Windows yerel hesap sıfırlama bambaşka bir iştir, kapsam dışı.

---

## Desteklenen donanımlar

| Faz / Model | Anakart | İşlemci | BIOS |
|---|---|---|---|
| Faz 1 Vestel Intel (Siyah) | VESTEL 14MB24A | Intel Core i3-2310M | AMI Aptio 4.6.5 |
| Faz 2 Vestel AMD (Gri) | VESTEL 14MB37C1 | AMD A10-5750M | AMI Aptio L0.30 |
| Faz 2 Vestel Intel (Gri) | VESTEL 14MB57 | Intel Core i3-4000M | AMI Aptio 4.6.5 |

> **Not (AMD 14MB37C1):** chipsec'in yüksek seviye `spi` modülü bu eski AMD FCH'yi
> tanımaz (`--pch` hatası). Araç bunu aşar: AMD'de SPI flash 4 GiB'ın altına **belleğe
> haritalıdır** (ROM penceresi) ve chipsec'in genel `read_phys_mem` ilkeliyle doğrudan
> okunur. Bu yüzden **canlı `bios read` AMD'de çalışır** (gerçek 14MB37C1'de doğrulandı).
> **Yazma** (`bios set/clear`) AMD'de henüz yok (bellek penceresi salt-okunur; SPI
> denetleyicisini sürmek gerekir) — AMD'de yazma için `--dump`/`--out` ya da Linux
> eta-112 (flashrom). Intel kartlar (14MB24A, 14MB57) chipsec ile oku+yaz tam çalışır.

---

## Gereksinimler

- **Windows** (çalışan sistem) ve **Yönetici (Administrator)** hakları.
- **Python 3**.
- Yalnız **okuma** için (Windows anahtarı, MAC): ek bir şey gerekmez — araç standart
  kütüphane + Windows DLL'lerini (ctypes) kullanır.
- **SPI flash okuma/yazma** için [CHIPSEC](https://github.com/chipsec/chipsec) + bir
  **çekirdek sürücüsü** (aşağıya bakın). Sürücünün yüklenebilmesi için **Secure Boot /
  HVCI kapalı** ve **test imzalama açık** olmalıdır (bu tahtalarda Secure Boot kapalıdır).
- **MAC değiştirme** için Realtek'in Windows PG aracı (ör. `PG8168` / `RtNicpg`).

---

## Kurulum

### Tek satır (önerilir)

Kurulum gerektirmez. **Yönetici** bir PowerShell açıp yapıştırın; betik yönetici değilse
kendini yükseltir, Python yoksa kurar, depoyu indirip menüyü açar:

```powershell
irm https://raw.githubusercontent.com/enseitankado/eta-112-win/main/baslat.ps1 | iex
```

(eta-112'nin `curl -fsSL .../baslat.sh | sudo bash` yönteminin Windows karşılığıdır.)

### Elle

```bat
python eta-112-win.py            :: menü
python eta-112-win.py kontrol    :: ön kurulum denetimi + CHIPSEC otomatik kurulum
```

Araç başlangıçta ön kurulumu **katmanlı** denetler (Python, yönetici, CHIPSEC paketi,
SPI sürücüsü, Secure Boot) ve eksik CHIPSEC paketini **derleyici gerektirmeden** kurar.

---

## CHIPSEC ve sürücü (SPI erişimi)

Windows'ta canlı SPI erişimi **iki katman** ister; `kontrol` komutu ikisini ayrı denetler.

**1) CHIPSEC Python paketi.** PyPI'deki `pip install chipsec` temiz bir tahtada iki
nedenle sorun çıkarır: (a) kaynaktan `EfiCompressor` C uzantısını derler ve *Microsoft
Visual C++ Build Tools* ister; (b) paket önceden derlenmiş çekirdek sürücüsü içermez.
Bu yüzden araç chipsec'i **depodaki hazır wheel'den** (`prebuilt/chipsec-*.whl`,
EfiCompressor'suz) kurar — derleyici ve indirme gerekmez. Yoksa EfiCompressor'suz
kaynak kurulumuna düşer. Hepsi `python eta-112-win.py kontrol` ile yapılır.

**2) Çekirdek sürücüsü** (asıl kapı). CHIPSEC paketi kurulu olsa da SPI, sürücü
yüklenmeden çalışmaz (`CHIPSEC Windows Driver Not Found`). Güncel chipsec'in Windows
yardımcısı `windowshelper`'dır ve kendi sürücüsünü (`chipsec_hlpr.sys`) ister. Sürücüyü
sağlamak için yönetici PowerShell'de:

```powershell
powershell -ExecutionPolicy Bypass -File tools\surucu-kur.ps1
```

- **Varsayılan (HIZLI):** depodaki **hazır sürücüyü** (`prebuilt\chipsec_hlpr.sys`)
  kullanır → Visual Studio, WDK, .NET kurulumu ve uzun derleme **atlanır**. Yalnız bir
  test sertifikası üretip sürücüyü imzalar (yerleşik `Set-AuthenticodeSignature`; Windows
  SDK gerekmez), yerine koyar ve `bcdedit /set testsigning on` ile test imzalamayı açar.
- **Kaynaktan derleme (`-Build`):** chipsec kaynağından `chipsec_hlpr.sys`'i Visual
  Studio + WDK + .NET (MSBuild) ile derler (eksikse .NET 4.8'i kurar; VS/WDK yoksa tam
  komutu yazar). Uzun sürer; bu yüzden hazır sürücü önerilir.

Her iki yolda da son adım: **yeniden başlatma** (test imzalama reboot ile etkin olur) →
`python eta-112-win.py bios read`.

> **Not:** Eski chipsec'teki RWEverything (`rwe`) yardımcısı — imzalı `RwDrv.sys` ile
> reboot'suz yüklenen yol — chipsec 1.9'da kaldırıldı; rwe'li son sürüm (1.8) modern
> Python'da (3.12) çalışmaz. Bu yüzden güncel kurulumda geçerli değildir.

Sürücü olmadan da [çevrimdışı mod](#çevrimdışı-mod---dump-ve---out) tam çalışır.

---

## Komut başvurusu

Yönetici bir CMD/PowerShell açın. Her komuta `--json` eklenirse makine-okur çıktı verir
(sözleşme üst proje eta-112 ile aynıdır); her komutun `-h` yardımı vardır.

```bat
python eta-112-win.py                                   :: etkileşimli menü

python eta-112-win.py bios info                         :: model / destek
python eta-112-win.py bios read                         :: parolaları oku (CHIPSEC)
python eta-112-win.py bios set --yonetici PAROLA         :: yönetici parolası ayarla
python eta-112-win.py bios set --kullanici PAROLA        :: kullanıcı parolası ayarla
python eta-112-win.py bios set --koruma setup|always    :: parola ne zaman sorulsun
python eta-112-win.py bios clear <all|yonetici|kullanici>:: parola sil
python eta-112-win.py bios calibrate yonetici PAROLA    :: bilinen parolayla keystream doğrula

python eta-112-win.py mac read                          :: MAC(ler) + Faz OUI durumu
python eta-112-win.py mac check 00:09:DF:12:34:56       :: yazmadan önce sına
python eta-112-win.py mac set  00:09:DF:12:34:56         :: (Windows'ta vendor aracı gerekir)

python eta-112-win.py wkey read                         :: Windows ürün anahtarını göster
python eta-112-win.py wkey set XXXXX-XXXXX-XXXXX-XXXXX-XXXXX

python eta-112-win.py kontrol                           :: ön kurulum denetimi
```

---

## Çevrimdışı mod: `--dump` ve `--out`

Sürücü olmadan, donanıma dokunmadan çalışır — geliştirme/doğrulama ve harici flashlama için.

```bat
:: bir ROM dökümünden oku (yazma yok, sürücüsüz)
python eta-112-win.py bios read --dump dump.bin

:: dry-run yazma: --dump kaynağını düzenleyip sonucu --out dosyasına yazar (flash'a dokunmaz)
python eta-112-win.py bios set --yonetici PAROLA --dump dump.bin --out yeni.bin
python eta-112-win.py bios clear all --dump dump.bin --out temiz.bin
```

`--dump` ile tam çip dökümü (CHIPSEC `spi dump` ile alınmış `.bin`) kullanılır. `--out`
ile üretilen imaj, harici bir programlayıcıyla yazılabilir ya da incelenebilir.

---

## Menü ve kısayollar

- Ok tuşlarıyla gezin, **Enter** ile seç, **1–9** doğrudan seçer.
- **Esc:** alt menülerde bir üst menüye döner; **ana menüde iki kez Esc** programdan çıkar
  (ilk Esc "Çıkış"ı işaretler ve uyarır).
- **Çıkışta** araç, geliştirici **Özgür Koca**'ya ([ozgurkoca.com](https://ozgurkoca.com))
  geri bildirim göndermek isteyip istemediğinizi sorar. İsterseniz yazdığınız mesaj
  `ntfy.sh` üzerinden **`eta-112`** konusuna iletilir (yalnız `urllib`; ek paket yok).
  Mesaja yalnız cihaz modeli bağlam olarak eklenir — kişisel bilgi gönderilmez.

---

## İşlem süreleri

Canlı `bios read/set/clear` ve `wkey set`, CHIPSEC ile **tüm SPI çipini (~8 MiB)** döker;
yazma ayrıca erase + write + geri-oku yapar. Bu nedenle:

- "`Durum: ✓ DESTEKLENİYOR …`" satırından sonra **10–40 sn** sessiz bir bekleme olabilir.
  Araç bu sırada "SPI flash okunuyor… lütfen bekleyin" bilgilendirmesi yazar — **program
  donmamıştır**.
- Yazma işlemi sırasında (`SPI flash'a yazılıyor…`) işlemi **kesmeyin / kapatmayın**.

---

## Doğrulama ve güvenlik

- Her yazma **geri-oku ile doğrulanır**. Değişiklik gerçekten flash'a işlemediyse araç
  "yazma donanımda etkili olmadı" der (yanlış "başarılı" demez).
- Yazma yalnız **aktif parola girişinin** 4 KiB sektörüne (MSDM için yalnız ilgili
  sektöre) yapılır; boot bloğuna dokunulmaz.
- Değişikliğin etkili olması için **yeniden başlatma** gerekir.
- `--dump` okuma ve `--out` dry-run yazma donanıma dokunmaz; yeni bir modeli doğrularken
  `calibrate` kullanın.

---

## Canlı yazma ve donanım notları

Canlı BIOS parolası yazma **VESTEL 14MB57'de gerçek donanımda doğrulanmıştır** (parola
değiştir → oku → eski haline getir turu, her adımda geri-oku ile `verified`). Canlı
flash yazmanın **donanımda tutması** için şunlar gerekir:

- **Secure Boot kapalı** olmalı (sürücü yüklensin).
- **BIOS Write Enable (BIOSWE)** açık olmalı. Araç yazmadan önce `spi disable-wp` ile
  BIOSWE'yi açar (Linux'ta `flashrom` bunu kendi yapar). BIOSWE=0 iken chipsec "tamamlandı"
  dese de flash değişmez.
- Bazı kartlarda BIOS bölgesi **flash çip seviyesinde** (Status Register blok-koruma) ya
  da descriptor bölge erişimiyle yazma korumalı olabilir; bu durumda OS altından yazma
  tutmayabilir. Araç bunu geri-oku doğrulamasıyla yakalar ve açıkça bildirir.

> ⚠️ Yanlış yazma BIOS'u kullanılamaz (brick) hale getirebilir. Yazmadan önce tam döküm
> yedeği alın (`chipsec_util spi dump yedek.bin`) ve mümkünse bir tezgah tahtasında sınayın.

---

## Geliştirme ve testler

Donanım gerektirmeyen regresyon testleri (sentetik AMI NVAR imajı, menü ESC davranışı,
geri bildirim akışı):

```bat
python tests\test_bios_roundtrip.py
python tests\test_menu_esc.py
python tests\test_feedback.py
```

---

## Sorun giderme

- **`CHIPSEC Windows Driver Not Found`** → sürücü yok/yüklenemiyor. `tools\surucu-kur.ps1`
  çalıştırın, sonra yeniden başlatın. Secure Boot kapalı ve test imzalama açık olmalı.
- **`No module named chipsec_util`** → chipsec kurulu değil. `python eta-112-win.py kontrol`.
- **`To specify a pch please use --pch` / `correct configuration is not loaded`** →
  chipsec'in `spi` modülü AMD FCH'yi tanımaz. **Okuma** için sorun değil: araç AMD'de
  flash'ı bellek-haritalı ROM penceresinden okur (`bios read` çalışır). Yalnız **yazma**
  AMD'de yok; `--dump`/`--out` ya da Linux eta-112 kullanın.
- **`Copy-Item … başka bir işlem tarafından kullanıldığından … chipsec_hlpr.sys …`** →
  yüklü chipsec sürücüsü dosyayı kilitliyor. `surucu-kur.ps1` artık kopyadan önce
  servisi durdurur; elle: yönetici cmd'de `sc stop chipsec_hlpr` ve `sc delete
  chipsec_hlpr`, chipsec kullanan pencereleri kapatıp tekrar deneyin.
- **Yazma "etkili olmadı"** → [Canlı yazma notları](#canlı-yazma-ve-donanım-notları)na
  bakın (BIOSWE / çip blok-koruma).
- **"DESTEKLENİYOR" sonrası uzun bekleme** → normaldir; SPI dökümü sürüyor (bkz.
  [İşlem süreleri](#işlem-süreleri)).
- **Model "DESTEKLENMİYOR"** → yalnız tablodaki kart+BIOS sürümleri desteklenir; aynı kart
  farklı BIOS ise `calibrate` ile doğrulayın.

---

## Lisans

- Geliştirici: **Özgür Koca** — [ozgurkoca.com](https://ozgurkoca.com)
- Lisans: **GPL-3.0-or-later** (üst proje eta-112 ile aynı).
- Üst proje: <https://github.com/enseitankado/eta-112>
