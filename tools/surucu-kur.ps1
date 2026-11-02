<#
  SPDX-License-Identifier: GPL-3.0-or-later
  eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>

  CANLI SPI icin CHIPSEC cekirdek surucusunu (chipsec_hlpr.sys) kur.

  Guncel chipsec Windows'ta kendi KMDF surucusunu ister; bu surucu hazir gelmez,
  kaynaktan WDK ile derlenir. Bu script tum adimlari otomatiklestirir:
    1. On kosullari dogrular (yonetici, Secure Boot kapali, Visual Studio + WDK)
    2. Kurulu chipsec'in surumunu bulup AYNI surumun kaynagini indirir (surucu kaynagi)
    3. chipsec_hlpr.vcxproj'u msbuild ile derler (x64)
    4. Kendinden-imzali bir TEST sertifikasi uretir, surucuyu imzalar, sertifikayi guvenir
    5. chipsec_hlpr.sys'i chipsec'in windowshelper'inin aradigi klasore kopyalar
    6. Test imzalamayi acar ve YENIDEN BASLATMA gerektigini bildirir

  Reboot sonrasi dogrulama:  python eta-112-win.py bios read

  !!! Surucu derlemek icin Visual Studio (C++ is yuku) + Windows Driver Kit (WDK)
      kurulu olmalidir. Yoksa script nasil kurulacagini soyler ve durur.
  !!! Secure Boot KAPALI olmalidir (bu tahtalarda kapalidir).
#>
[CmdletBinding()]
param(
    [string]$Python = "",            # bos ise otomatik bulunur
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
function Yaz($m, $c = "Gray") { Write-Host "  $m" -ForegroundColor $c }
function Dur($m) { Write-Host "  HATA: $m" -ForegroundColor Red; exit 1 }

# ---- 0) yonetici ----
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
          ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Dur "Yonetici (Administrator) PowerShell gerekir." }

# ---- 1) Secure Boot ----
try { if (Confirm-SecureBootUEFI) {
    Dur "Secure Boot ACIK. Kendi-imzali surucu yuklenemez. BIOS'tan kapatip tekrar deneyin."
} Yaz "Secure Boot: kapali" "Green" } catch { Yaz "Secure Boot: yok/legacy — sorun degil" "Green" }

# ---- 2) Python + chipsec ----
if (-not $Python) {
    foreach ($c in "python","py") {
        $p = Get-Command $c -ErrorAction SilentlyContinue
        if ($p -and (& $p.Source --version 2>&1) -match "Python 3") { $Python = $p.Source; break }
    }
}
if (-not $Python) { Dur "Python 3 bulunamadi." }
Yaz "Python: $Python" "Green"

$chipsecDir = & $Python -c "import chipsec, os; print(os.path.dirname(chipsec.__file__))" 2>$null
if (-not $chipsecDir) {
    Yaz "chipsec kurulu degil — araci bir kez calistirin ('python eta-112-win.py kontrol') ya da:" "Yellow"
    Dur "python eta-112-win.py kontrol   (chipsec'i derleyicisiz kurar), sonra bu script'i tekrar calistirin."
}
$chipsecVer = & $Python -c "import chipsec; print(open(__import__('os').path.join(r'$chipsecDir','VERSION')).read().strip())" 2>$null
Yaz "chipsec: $chipsecVer  ($chipsecDir)" "Green"
$driverDest = Join-Path $chipsecDir "helper\windows\windows_amd64"

# ---- 3) Visual Studio + WDK ----
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    Write-Host ""
    Yaz 'Visual Studio / Build Tools bulunamadi. Surucu derlemek icin sunlar gerekir:' 'Yellow'
    Yaz '  1) Visual Studio 2022 Build Tools (C++ is yuku). winget ile:' 'Yellow'
    Yaz '     winget install --id Microsoft.VisualStudio.2022.BuildTools -e' 'Yellow'
    Yaz '       --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"' 'Yellow'
    Yaz '  2) Windows Driver Kit (WDK): https://learn.microsoft.com/windows-hardware/drivers/download-the-wdk' 'Yellow'
    Yaz '     (Spectre-azaltilmis VC kitapliklari + WDK VS eklentisini de kurun.)' 'Yellow'
    Dur "Yukaridakileri kurup bu script'i tekrar calistirin."
}
$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { Dur "VC++ is yuku (C++ Build Tools) kurulu degil. Yukaridaki winget komutuyla kurun." }
Yaz "Visual Studio: $vsPath" "Green"
$vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $vcvars)) { Dur "vcvars64.bat bulunamadi: $vcvars" }

# ---- 4) chipsec kaynagini indir (surucu kaynagi paket icinde yok) ----
$work = Join-Path $env:TEMP ("eta112_drv_" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force $work | Out-Null
Yaz "chipsec $chipsecVer kaynagi indiriliyor (surucu kaynagi icin)..." "Gray"
& $Python -m pip download "chipsec==$chipsecVer" --no-deps --no-binary=:all: --dest $work 2>&1 | Out-Null
$tar = Get-ChildItem $work -Filter "chipsec-*.tar.gz" | Select-Object -First 1
if (-not $tar) { Dur "chipsec kaynagi indirilemedi." }
tar -xzf $tar.FullName -C $work
$drvSrc = Get-ChildItem $work -Directory -Filter "chipsec-*" |
          ForEach-Object { Join-Path $_.FullName "drivers\windows\chipsec" } |
          Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $drvSrc) { Dur "drivers\windows\chipsec kaynagi bulunamadi." }
Yaz "Surucu kaynagi: $drvSrc" "Green"

# ---- 5) derle (msbuild, x64) ----
Yaz "Surucu derleniyor (msbuild, $Configuration x64)... WDK gerekir." "Cyan"
$proj = Join-Path $drvSrc "chipsec_hlpr.vcxproj"
$bat = Join-Path $work "build.cmd"
@"
@echo off
call "$vcvars"
cd /d "$drvSrc"
msbuild /t:Build /p:Configuration=$Configuration /p:Platform=x64 "$proj"
"@ | Set-Content -Path $bat -Encoding ascii
cmd /c "`"$bat`""
$sys = Get-ChildItem $drvSrc -Recurse -Filter "chipsec_hlpr.sys" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $sys) {
    Dur "Derleme basarisiz: chipsec_hlpr.sys uretilmedi. WDK (KMDF, WindowsKernelModeDriver10.0 toolset) kurulu mu?"
}
Yaz "Derlendi: $($sys.FullName)" "Green"

# ---- 6) test sertifikasi + imzala + guven ----
Yaz "Test sertifikasi uretiliyor ve surucu imzalaniyor..." "Gray"
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=eta-112-win Test Driver" `
          -CertStoreLocation Cert:\LocalMachine\My -KeyUsage DigitalSignature `
          -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")
$store = "Cert:\LocalMachine\My\$($cert.Thumbprint)"
Export-Certificate -Cert $store -FilePath (Join-Path $work "etatest.cer") | Out-Null
Import-Certificate -FilePath (Join-Path $work "etatest.cer") -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
Import-Certificate -FilePath (Join-Path $work "etatest.cer") -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "x64" } | Select-Object -First 1
if (-not $signtool) { Dur "signtool.exe bulunamadi (Windows SDK kurulu mu?)." }
& $signtool.FullName sign /v /fd SHA256 /sha1 $cert.Thumbprint /t http://timestamp.digicert.com $sys.FullName
if ($LASTEXITCODE -ne 0) { Dur "Imzalama basarisiz." }

# ---- 7) yerine kopyala ----
New-Item -ItemType Directory -Force $driverDest | Out-Null
Copy-Item $sys.FullName (Join-Path $driverDest "chipsec_hlpr.sys") -Force
Yaz "Surucu kopyalandi: $driverDest\chipsec_hlpr.sys" "Green"

# ---- 8) test imzalamayi ac + reboot ----
Write-Host ""
Yaz "Test imzalama aciliyor (bcdedit)..." "Cyan"
bcdedit /set testsigning on | Out-Null
Write-Host ""
Yaz "TAMAM. Son iki adim:" "Green"
Yaz "  1) Bilgisayari YENIDEN BASLATIN (test imzalama ancak reboot sonrasi etkin olur)." "Yellow"
Yaz "  2) Yonetici PowerShell: python eta-112-win.py bios read" "Yellow"
Write-Host ""
Yaz "Not: testsigning kapatmak icin: bcdedit /set testsigning off  (+reboot)" "Gray"
