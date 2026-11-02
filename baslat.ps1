# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win baslatici — eta-112'nin baslat.sh'inin Windows karsiligi.
# Copyright (C) 2026 Ozgur Koca <https://ozgurkoca.com>
#
# Uzaktan calistirma (yonetici PowerShell):
#   irm https://raw.githubusercontent.com/enseitankado/eta-112-win/main/baslat.ps1 | iex
#
# Yaptigi: (1) yonetici degilse kendini yukseltir, (2) Python yoksa kurar,
# (3) depoyu indirip acar, (4) eta-112-win.py menusunu baslatir. CHIPSEC gibi
# flash on-kosullari aracin kendi baslangic denetiminde (kontrol) tamamlanir.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$REPO       = "enseitankado/eta-112-win"
$BRANCH     = "main"
$ZIP_URL    = "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip"
$SELF_URL   = "https://raw.githubusercontent.com/$REPO/$BRANCH/baslat.ps1"

function Yaz($m, $renk="Gray") { Write-Host "  $m" -ForegroundColor $renk }

# ---- 1) Yonetici yukseltme ----
$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Yaz "Yonetici haklari gerekiyor — yukseltiliyor..." "Yellow"
    $cmd = "irm $SELF_URL | iex"
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile","-ExecutionPolicy","Bypass","-Command",$cmd
    return
}

Write-Host ""
Yaz "ETA-112-WIN baslatici" "Cyan"
Write-Host ""

# ---- 2) Python ----
function Python-Bul {
    foreach ($c in @("python","py")) {
        $p = Get-Command $c -ErrorAction SilentlyContinue
        if ($p) {
            try {
                $v = & $p.Source --version 2>&1
                if ($v -match "Python 3") { return $p.Source }
            } catch {}
        }
    }
    return $null
}

$py = Python-Bul
if (-not $py) {
    Yaz "Python bulunamadi — kuruluyor..." "Yellow"
    $kuruldu = $false
    # 2a) winget (varsa)
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            winget install -e --id Python.Python.3.12 --silent `
                --accept-source-agreements --accept-package-agreements
            $kuruldu = $true
        } catch { Yaz "winget ile kurulum basarisiz: $_" "Yellow" }
    }
    # 2b) python.org resmi kurulum (sessiz)
    if (-not $kuruldu) {
        try {
            $ver = "3.12.7"
            $exe = "$env:TEMP\python-$ver-amd64.exe"
            Yaz "python.org'dan indiriliyor (python $ver)..." "Gray"
            Invoke-WebRequest "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe" `
                -OutFile $exe -UseBasicParsing
            Yaz "sessiz kuruluyor..." "Gray"
            Start-Process $exe -Wait -ArgumentList `
                "/quiet","InstallAllUsers=1","PrependPath=1","Include_pip=1"
            $kuruldu = $true
        } catch { Yaz "python.org kurulumu basarisiz: $_" "Red" }
    }
    # PATH tazele
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path","User")
    $py = Python-Bul
    if (-not $py) {
        Yaz "Python kurulamadi. Lutfen https://www.python.org/downloads/ adresinden" "Red"
        Yaz "Python 3'u kurun (PATH'e ekleyin) ve betigi tekrar calistirin." "Red"
        return
    }
}
Yaz "Python: $py" "Green"

# ---- 3) Depoyu indir + ac ----
$kok = Join-Path $env:TEMP "eta-112-win"
if (Test-Path $kok) { Remove-Item $kok -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $kok | Out-Null
$zip = Join-Path $env:TEMP "eta-112-win.zip"
Yaz "Depo indiriliyor..." "Gray"
Invoke-WebRequest $ZIP_URL -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $kok -Force
$surumDir = Get-ChildItem $kok -Directory | Select-Object -First 1
$giris = Join-Path $surumDir.FullName "eta-112-win.py"
if (-not (Test-Path $giris)) {
    Yaz "eta-112-win.py bulunamadi (indirme bozuk olabilir)." "Red"
    return
}

# ---- 4) Calistir ----
Write-Host ""
Yaz "Baslatiliyor: $giris" "Cyan"
Write-Host ""
& $py $giris @args
