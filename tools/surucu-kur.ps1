<#
  SPDX-License-Identifier: GPL-3.0-or-later
  eta-112-win — Copyright (C) 2026 Ozgur Koca <https://ozgurkoca.com>

  CANLI SPI icin CHIPSEC cekirdek surucusunu (chipsec_hlpr.sys) kurar.

  HIZLI YOL (varsayilan): Depodaki HAZIR surucuyu (prebuilt\chipsec_hlpr.sys)
  kullanir; boylece Visual Studio + WDK + .NET kurulumu ve uzun derleme ATLANIR.
  Yalnizca: test sertifikasi uret + surucuyu imzala + yerine koy + testsigning ac.

  KAYNAKTAN DERLEME (-Build ya da hazir surucu yoksa): chipsec kaynagini indirip
  WDK ile derler (VS2022 C++ Build Tools + WDK gerekir; yoksa nasil kurulacagini
  soyler). Derleme uzun surer; bu yuzden hazir surucu onerilir.

  Her iki yolda da sonunda YENIDEN BASLATMA gerekir (test imzalama reboot ile etkin).
  Reboot sonrasi dogrulama:  python eta-112-win.py bios read

  !!! Secure Boot KAPALI olmalidir (bu tahtalarda kapalidir).
#>
[CmdletBinding()]
param(
    [string]$Python = "",            # bos ise otomatik bulunur
    [string]$Configuration = "Release",
    [switch]$Build                   # hazir surucu yerine kaynaktan derlemeye zorla
)

$ErrorActionPreference = "Stop"
function Yaz($m, $c = "Gray") { Write-Host "  $m" -ForegroundColor $c }
function Dur($m) { Write-Host "  HATA: $m" -ForegroundColor Red; exit 1 }

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Prebuilt = Join-Path $RepoRoot "prebuilt\chipsec_hlpr.sys"

# ---- 0) yonetici ----
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
          ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Dur "Yonetici (Administrator) PowerShell gerekir." }

# ---- 1) Secure Boot ----
try {
    if (Confirm-SecureBootUEFI) {
        Dur "Secure Boot ACIK. Kendi-imzali surucu yuklenemez. BIOS'tan kapatip tekrar deneyin."
    }
    Yaz "Secure Boot: kapali" "Green"
} catch { Yaz "Secure Boot: yok/legacy - sorun degil" "Green" }

# ---- 2) Python + chipsec ----
if (-not $Python) {
    foreach ($c in "python","py") {
        # Get-Command birden cok sonuc donebilir (gercek Python + Store takma adi);
        # gercek bir .Source'u olan ILK sonucu al, yoksa '& <dizi>' hatasi olur.
        $cmd = Get-Command $c -ErrorAction SilentlyContinue |
               Where-Object { $_.Source -and (Test-Path $_.Source) } | Select-Object -First 1
        if (-not $cmd) { continue }
        $src = [string]$cmd.Source
        $ver = & $src --version 2>&1
        if ("$ver" -match "Python 3") { $Python = $src; break }
    }
}
if (-not $Python) { Dur "Python 3 bulunamadi (python/py PATH'te mi?)." }
Yaz "Python: $Python" "Green"

$chipsecDir = & $Python -c "import chipsec, os; print(os.path.dirname(chipsec.__file__))" 2>$null
if (-not $chipsecDir) {
    Yaz "chipsec kurulu degil. Once: python eta-112-win.py kontrol  (chipsec'i derleyicisiz kurar)." "Yellow"
    Dur "chipsec kurulduktan sonra bu script'i tekrar calistirin."
}
Yaz "chipsec: $chipsecDir" "Green"
$driverDest = Join-Path $chipsecDir "helper\windows\windows_amd64"

# ---- 3) Surucuyu SAGLA: hazir (depo) ya da kaynaktan derle ----
$sysPath = $null
if ((Test-Path $Prebuilt) -and (-not $Build)) {
    $sysPath = $Prebuilt
    Yaz "Hazir surucu depodan kullaniliyor (derleme/VS/WDK ATLANDI):" "Green"
    Yaz "  $sysPath" "Green"
    Yaz "  (Kaynaktan derlemek icin: -Build)" "Gray"
} else {
    if ($Build) { Yaz "-Build verildi: kaynaktan derlenecek." "Cyan" }
    else { Yaz "Hazir surucu yok; kaynaktan derlenecek (uzun surebilir)." "Yellow" }

    # 3a) .NET Framework 4.x (MSBuild icin). Araç CALISMA ZAMANINDA .NET istemez;
    #     yalnizca bu derleme yolu icin gerekir. Eksikse resmi .NET 4.8 kurulur.
    $dotnet4 = $false
    try {
        $r = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -ErrorAction Stop
        if ($r.Release -ge 378389) { $dotnet4 = $true }
    } catch { $dotnet4 = $false }
    if ($dotnet4) {
        Yaz ".NET Framework 4.x: kurulu" "Green"
    } else {
        Yaz ".NET Framework 4.x yok; resmi .NET 4.8 sessiz kuruluyor..." "Yellow"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ndp = Join-Path $env:TEMP "ndp48-web.exe"
        Invoke-WebRequest "https://go.microsoft.com/fwlink/?linkid=2088631" -OutFile $ndp -UseBasicParsing
        $pn = Start-Process $ndp -ArgumentList "/q","/norestart" -Wait -PassThru
        Yaz ".NET 4.8 kurulum cikis kodu: $($pn.ExitCode) (3010 = reboot gerekli)" "Gray"
    }

    # 3b) Visual Studio + VC Build Tools
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        Write-Host ""
        Yaz 'Visual Studio / Build Tools bulunamadi. Surucu derlemek icin:' 'Yellow'
        Yaz '  winget install --id Microsoft.VisualStudio.2022.BuildTools -e' 'Yellow'
        Yaz '    --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"' 'Yellow'
        Yaz '  + WDK: https://learn.microsoft.com/windows-hardware/drivers/download-the-wdk' 'Yellow'
        Dur "Kurup tekrar calistirin (ya da hazir surucu kullanin)."
    }
    $vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vsPath) { Dur "VC++ is yuku kurulu degil." }
    Yaz "Visual Studio: $vsPath" "Green"
    $vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars64.bat"
    if (-not (Test-Path $vcvars)) { Dur "vcvars64.bat bulunamadi: $vcvars" }

    # 3c) WDK KMDF toolset entegre mi?
    $toolsetOk = Test-Path (Join-Path $vsPath "MSBuild\Microsoft\VC\v170\Platforms\x64\PlatformToolsets\WindowsKernelModeDriver10.0")
    if (-not $toolsetOk) {
        Write-Host ""
        Yaz "WindowsKernelModeDriver10.0 toolset VS'e entegre degil (WDK VSIX eksik)." "Yellow"
        Yaz "Sessiz ekleme (DOGRULANDI):" "Yellow"
        Yaz '  & "C:\Program Files (x86)\Microsoft Visual Studio\Installer\setup.exe" modify ^' 'Yellow'
        Yaz ('    --installPath "' + $vsPath + '" ^') 'Yellow'
        Yaz "    --add Component.Microsoft.Windows.DriverKit.BuildTools --quiet --norestart" "Yellow"
        Dur "WDK toolset'ini ekleyip tekrar calistirin (ya da hazir surucu kullanin)."
    }

    # 3d) chipsec kaynagini indir (surucu kaynagi PyPI sdist'te YOK; GitHub release'de)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $work = Join-Path $env:TEMP ("eta112_drv_" + [guid]::NewGuid().ToString("N").Substring(0,8))
    New-Item -ItemType Directory -Force $work | Out-Null
    Yaz "chipsec GitHub release kaynagi indiriliyor..." "Gray"
    $hdr = @{ "User-Agent" = "eta-112-win" }
    $rel = Invoke-RestMethod "https://api.github.com/repos/chipsec/chipsec/releases/latest" -Headers $hdr
    $zipUrl = ($rel.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1).browser_download_url
    if (-not $zipUrl) { $zipUrl = $rel.zipball_url }
    $zip = Join-Path $work "chipsec-src.zip"
    Invoke-WebRequest $zipUrl -OutFile $zip -Headers $hdr -UseBasicParsing
    Expand-Archive $zip -DestinationPath $work -Force
    $drvSrc = Get-ChildItem $work -Recurse -Directory -Filter "chipsec" -ErrorAction SilentlyContinue |
              ForEach-Object { $_.FullName } |
              Where-Object { Test-Path (Join-Path $_ "chipsec_hlpr.vcxproj") } | Select-Object -First 1
    if (-not $drvSrc) { Dur "chipsec_hlpr.vcxproj kaynagi bulunamadi." }
    Yaz "Surucu kaynagi: $drvSrc" "Green"

    # 3e) derle (SignMode=Off: projenin kendi TestSign adimi bozuk; imzayi biz atariz)
    Yaz "Surucu derleniyor (msbuild, $Configuration x64)..." "Cyan"
    $bat = Join-Path $work "build.cmd"
    @"
@echo off
call "$vcvars"
cd /d "$drvSrc"
msbuild /t:Build /p:Configuration=$Configuration /p:Platform=x64 /p:SignMode=Off "chipsec_hlpr.vcxproj"
"@ | Set-Content -Path $bat -Encoding ascii
    cmd /c "`"$bat`""
    $built = Get-ChildItem $drvSrc -Recurse -Filter "chipsec_hlpr.sys" -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $built) { Dur "Derleme basarisiz: chipsec_hlpr.sys uretilmedi." }
    $sysPath = $built.FullName
    Yaz "Derlendi: $sysPath" "Green"
}

# ---- 4) yerine kopyala ----
New-Item -ItemType Directory -Force $driverDest | Out-Null
$destSys = Join-Path $driverDest "chipsec_hlpr.sys"
Copy-Item $sysPath $destSys -Force
Yaz "Surucu kopyalandi: $destSys" "Green"

# ---- 5) test sertifikasi uret + guven + imzala (SDK/signtool GEREKTIRMEZ) ----
Yaz "Test sertifikasi uretiliyor ve surucu imzalaniyor..." "Gray"
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=eta-112-win Test Driver" `
          -CertStoreLocation Cert:\LocalMachine\My -KeyUsage DigitalSignature `
          -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")
$tmpCer = Join-Path $env:TEMP "eta112-testcert.cer"
Export-Certificate -Cert "Cert:\LocalMachine\My\$($cert.Thumbprint)" -FilePath $tmpCer | Out-Null
Import-Certificate -FilePath $tmpCer -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
Import-Certificate -FilePath $tmpCer -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null

# Yerlesik Set-AuthenticodeSignature (Windows'ta vardir; Windows SDK/signtool gerekmez)
$sig = Set-AuthenticodeSignature -FilePath $destSys -Certificate $cert -HashAlgorithm SHA256
if ($sig.Status -ne "Valid") {
    # yedek: SDK varsa signtool ile dene
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match "\\x64\\" } | Select-Object -First 1
    if ($signtool) { & $signtool.FullName sign /v /sm /fd SHA256 /sha1 $cert.Thumbprint $destSys }
}
$sig = Get-AuthenticodeSignature $destSys
if ($sig.Status -ne "Valid") { Dur "Imzalama basarisiz (durum: $($sig.Status))." }
Yaz "Imza: $($sig.Status)  ($($sig.SignerCertificate.Subject))" "Green"

# ---- 6) test imzalamayi ac ----
Write-Host ""
Yaz "Test imzalama aciliyor (bcdedit)..." "Cyan"
bcdedit /set testsigning on | Out-Null
Write-Host ""
Yaz "TAMAM. Son iki adim:" "Green"
Yaz "  1) Bilgisayari YENIDEN BASLATIN (test imzalama ancak reboot sonrasi etkin olur)." "Yellow"
Yaz "  2) Yonetici PowerShell: python eta-112-win.py bios read" "Yellow"
Write-Host ""
Yaz "Not: testsigning kapatmak icin: bcdedit /set testsigning off  (+reboot)" "Gray"
