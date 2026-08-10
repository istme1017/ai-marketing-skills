<#
.SYNOPSIS
  Instala ClipForge en Windows y crear un acceso directo para usarlo.

.DESCRIPTION
  Instala Python, ffmpeg, las dependencias y la fuente Montserrat ExtraBold.
  Deja todo listo en el disco D: por defecto, para no llenar C:.

  Ejecuta en PowerShell (no hace falta admin salvo para winget):

    .\install-windows.ps1

  Luego abre ClipForge con el acceso directo del escritorio, o:

    D:\ClipForge\start.bat
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "D:\ClipForge",
    [string]$ClipsDir   = "D:\ClipForge\clips",
    [int]$Port = 8899
)

$ErrorActionPreference = "Continue"
function ok($m)   { Write-Host "  [OK] $m"   -ForegroundColor Green }
function bad($m)  { Write-Host "  [X]  $m"   -ForegroundColor Red }
function step($m) { Write-Host "`n$m" -ForegroundColor White }

$failed = 0

step "1. Verificando disco"
$drive = (Split-Path $InstallDir -Qualifier)
if (-not (Test-Path $drive)) {
    bad "El disco $drive no existe. Usa -InstallDir C:\ClipForge si solo tienes C:."
    exit 1
}
$free = (Get-PSDrive -Name $drive.TrimEnd(':')).Free
ok ("Libre en {0} {1:N1} GB" -f $drive, ($free / 1GB))
if ($free -lt 20GB) {
    bad "Menos de 20 GB libres. Cada video largo puede usar ~10 GB mientras procesa."
}

step "2. Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) {
    bad "Python no encontrado. Instalando con winget..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    Write-Host "  Cierra y vuelve a abrir PowerShell, luego repite este script." -ForegroundColor Yellow
    exit 1
}
ok ((& $py.Source --version) 2>&1)

step "3. ffmpeg"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    ok "ffmpeg ya instalado"
} else {
    Write-Host "  Instalando ffmpeg con winget..."
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) { ok "ffmpeg instalado" }
    else {
        bad "No se pudo instalar ffmpeg automaticamente."
        Write-Host "  Descargalo de https://www.gyan.dev/ffmpeg/builds/ y agrega la carpeta bin al PATH." -ForegroundColor Yellow
        $failed = 1
    }
}

step "4. Carpetas"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $ClipsDir   -Force | Out-Null
ok "$InstallDir"
ok "$ClipsDir"

step "5. Copiando ClipForge"
$src = Join-Path $PSScriptRoot "*"
Copy-Item -Path $src -Destination $InstallDir -Recurse -Force -Exclude @("clips", "__pycache__")
ok "Codigo copiado"

step "6. Dependencias de Python"
& $py.Source -m pip install --quiet --upgrade pip 2>&1 | Out-Null
# opencv-python must stay below 5: OpenCV 5 removed CascadeClassifier,
# which is what the face-centred crop uses.
$pkgs = @("faster-whisper", "yt-dlp", "pillow", "fonttools", "numpy", "opencv-python<5")
foreach ($p in $pkgs) {
    & $py.Source -m pip install --quiet --upgrade $p 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { ok $p } else { bad "$p fallo"; $failed = 1 }
}

step "7. Fuente Montserrat ExtraBold"
# La fuente variable de Google tiene peso por defecto 100 (Thin). Si se instala
# tal cual, libass dibuja letras finisimas y los subtitulos no se parecen en
# nada al estilo Klap. Por eso se fija una instancia estatica en peso 800.
$fontDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"
New-Item -ItemType Directory -Path $fontDir -Force | Out-Null
$target = Join-Path $fontDir "MontserratExtraBold-static.ttf"

if (Test-Path $target) {
    ok "Fuente ya instalada"
} else {
    $tmp = Join-Path $env:TEMP "Montserrat-var.ttf"
    $url = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
    try {
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        $script = @"
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
f = TTFont(r'$tmp')
i = instancer.instantiateVariableFont(f, {'wght': 800})
i['name'].setName('Montserrat ExtraBold', 1, 3, 1, 0x409)
i['name'].setName('Regular', 2, 3, 1, 0x409)
i['name'].setName('Montserrat ExtraBold', 4, 3, 1, 0x409)
i.save(r'$target')
"@
        $script | & $py.Source -
        if (Test-Path $target) {
            New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts" `
                -Name "Montserrat ExtraBold (TrueType)" -PropertyType String `
                -Value $target -Force | Out-Null
            ok "Fuente instalada en peso 800"
        } else { bad "No se pudo crear la fuente"; $failed = 1 }
    } catch {
        bad "No se pudo descargar la fuente: $_"
        Write-Host "  Los subtitulos usaran otra fuente y no coincidiran con el estilo." -ForegroundColor Yellow
    }
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

step "8. Creando acceso directo"
$bat = @"
@echo off
title ClipForge
cd /d "$InstallDir"
set CLIPFORGE_OUT=$ClipsDir
echo Abriendo ClipForge en http://localhost:$Port
start "" http://localhost:$Port
python -m clipforge.web --port $Port --out "$ClipsDir"
pause
"@
$batPath = Join-Path $InstallDir "start.bat"
Set-Content -Path $batPath -Value $bat -Encoding ASCII
ok $batPath

try {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $sc = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop "ClipForge.lnk"))
    $sc.TargetPath = $batPath
    $sc.WorkingDirectory = $InstallDir
    $sc.Description = "ClipForge - clips verticales"
    $sc.Save()
    ok "Acceso directo en el escritorio"
} catch { bad "No se pudo crear el acceso directo: $_" }

step "Resultado"
if ($failed -eq 0) {
    Write-Host "  Instalacion completa." -ForegroundColor Green
    Write-Host "  Abre ClipForge con el acceso directo del escritorio.`n"
    Write-Host "  La primera vez, whisper descarga su modelo (~500 MB). Es normal que tarde.`n" -ForegroundColor DarkGray
} else {
    Write-Host "  Termino con errores. Revisa las lineas [X] de arriba.`n" -ForegroundColor Red
}
exit $failed
