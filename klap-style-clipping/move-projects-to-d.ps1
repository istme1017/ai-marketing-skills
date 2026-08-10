<#
.SYNOPSIS
  Mueve los proyectos locales del disco C: al disco D: y redirige las carpetas
  temporales y de caché, para que C: deje de llenarse.

.DESCRIPTION
  DRY RUN POR DEFECTO. Sin -Execute solo muestra qué haría; no mueve nada.

  Qué hace con -Execute:
    1. Copia la carpeta de proyectos a D: con robocopy (verifica antes de borrar).
    2. Deja un "junction" (enlace) en la ruta vieja de C:, para que cualquier
       programa con la ruta escrita a mano siga funcionando sin cambios.
    3. Manda TEMP y TMP del usuario a D:\Temp.
    4. Manda la caché de yt-dlp a D:\yt-dlp-cache.

  IMPORTANTE: cierra ClipForge, VS Code, Codex y cualquier terminal abierta en
  esas carpetas ANTES de ejecutar con -Execute. Un archivo abierto bloquea la
  mudanza y la deja a medias.

.EXAMPLE
  # 1. Ver qué haría (no toca nada):
  .\move-projects-to-d.ps1 -Source "C:\Users\17875\Documents\Codex" -Dest "D:\Codex"

.EXAMPLE
  # 2. Hacerlo de verdad:
  .\move-projects-to-d.ps1 -Source "C:\Users\17875\Documents\Codex" -Dest "D:\Codex" -Execute
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Dest,

    [switch]$Execute,
    [switch]$NoJunction,
    [string]$TempDir  = 'D:\Temp',
    [string]$CacheDir = 'D:\yt-dlp-cache'
)

$ErrorActionPreference = 'Continue'

function Show-Size([long]$b) {
    if ($b -ge 1GB) { return ('{0:N2} GB' -f ($b / 1GB)) }
    if ($b -ge 1MB) { return ('{0:N0} MB' -f ($b / 1MB)) }
    return ('{0:N0} KB' -f ($b / 1KB))
}
function Titulo($t) { Write-Host "`n$t" -ForegroundColor White }

# ------------------------------------------------------------- validaciones
if (-not (Test-Path $Source)) { Write-Host "No existe el origen: $Source" -ForegroundColor Red; exit 1 }
$Source = (Resolve-Path $Source).Path

$destDrive = (Split-Path $Dest -Qualifier)
if (-not (Test-Path $destDrive)) {
    Write-Host "El disco $destDrive no existe o no esta montado." -ForegroundColor Red; exit 1
}

$size = (Get-ChildItem $Source -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
$free = (Get-PSDrive -Name $destDrive.TrimEnd(':')).Free

Titulo "=== Resumen ==="
Write-Host ("  Origen : {0}" -f $Source)
Write-Host ("  Destino: {0}" -f $Dest)
Write-Host ("  Tamano : {0}" -f (Show-Size $size)) -ForegroundColor Yellow
Write-Host ("  Libre en {0} {1}" -f $destDrive, (Show-Size $free)) -ForegroundColor Cyan

if ($free -lt $size * 1.1) {
    Write-Host "  AVISO: puede que no entre en $destDrive." -ForegroundColor Red
}

# ------------------------------------------------------------- procesos abiertos
Titulo "=== Procesos que podrian bloquear la mudanza ==="
$locking = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Source, [StringComparison]::OrdinalIgnoreCase) }
if ($locking) {
    $locking | ForEach-Object { Write-Host ("  {0} (PID {1})" -f $_.ProcessName, $_.Id) -ForegroundColor Red }
    Write-Host "  Cierralos antes de usar -Execute." -ForegroundColor Red
} else {
    Write-Host "  Ninguno detectado." -ForegroundColor Green
}

Titulo "=== Cambios de configuracion que se aplicaran ==="
Write-Host ("  TEMP y TMP del usuario -> {0}" -f $TempDir)
Write-Host ("  Cache de yt-dlp        -> {0}" -f $CacheDir)
if (-not $NoJunction) { Write-Host ("  Enlace (junction) en    {0} -> {1}" -f $Source, $Dest) }

if (-not $Execute) {
    Write-Host "`nDRY RUN: no se movio nada. Agrega -Execute para hacerlo.`n" -ForegroundColor Cyan
    exit 0
}

if ($locking) {
    Write-Host "`nAbortado: hay procesos usando la carpeta. Cierralos y repite.`n" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------- copia
Titulo "=== 1. Copiando a $Dest ==="
New-Item -ItemType Directory -Path $Dest -Force | Out-Null
robocopy $Source $Dest /E /R:2 /W:2 /NFL /NDL /NJH /NP | Out-Null
$rc = $LASTEXITCODE

if ($rc -ge 8) {
    Write-Host "  robocopy fallo (codigo $rc). NO se borro nada del origen." -ForegroundColor Red
    exit 1
}
Write-Host "  Copia terminada (codigo $rc)." -ForegroundColor Green

# ------------------------------------------------------------- verificacion
Titulo "=== 2. Verificando ==="
$sn = (Get-ChildItem $Source -Recurse -File -ErrorAction SilentlyContinue).Count
$dn = (Get-ChildItem $Dest   -Recurse -File -ErrorAction SilentlyContinue).Count
Write-Host ("  Archivos origen: {0} / destino: {1}" -f $sn, $dn)

if ($dn -lt $sn) {
    Write-Host "  Faltan archivos en el destino. NO se borra el origen. Revisa manualmente." -ForegroundColor Red
    exit 1
}
Write-Host "  Verificacion OK." -ForegroundColor Green

# ------------------------------------------------------------- borrar origen + junction
Titulo "=== 3. Liberando C: ==="
try {
    Remove-Item -LiteralPath $Source -Recurse -Force -ErrorAction Stop
    Write-Host ("  Liberados {0} en C:." -f (Show-Size $size)) -ForegroundColor Green
} catch {
    Write-Host "  No se pudo borrar el origen: $_" -ForegroundColor Red
    Write-Host "  Los datos YA estan en $Dest. Borra la carpeta vieja a mano." -ForegroundColor Yellow
    exit 1
}

if (-not $NoJunction) {
    try {
        New-Item -ItemType Junction -Path $Source -Target $Dest -ErrorAction Stop | Out-Null
        Write-Host ("  Enlace creado: {0} -> {1}" -f $Source, $Dest) -ForegroundColor Green
        Write-Host "  Las rutas viejas siguen funcionando." -ForegroundColor DarkGray
    } catch {
        Write-Host "  No se pudo crear el enlace (requiere admin): $_" -ForegroundColor Yellow
    }
}

# ------------------------------------------------------------- temp y cache
Titulo "=== 4. Redirigiendo TEMP y cache ==="
New-Item -ItemType Directory -Path $TempDir  -Force | Out-Null
New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null

[Environment]::SetEnvironmentVariable('TEMP', $TempDir, 'User')
[Environment]::SetEnvironmentVariable('TMP',  $TempDir, 'User')
Write-Host ("  TEMP y TMP -> {0}" -f $TempDir) -ForegroundColor Green

# yt-dlp lee su config de %APPDATA%\yt-dlp\config
$ytConfDir = Join-Path $env:APPDATA 'yt-dlp'
New-Item -ItemType Directory -Path $ytConfDir -Force | Out-Null
$ytConf = Join-Path $ytConfDir 'config'
$line = "--cache-dir `"$CacheDir`""
if ((Test-Path $ytConf) -and (Select-String -Path $ytConf -Pattern 'cache-dir' -Quiet)) {
    Write-Host "  yt-dlp ya tenia cache-dir configurado; no se toco." -ForegroundColor DarkGray
} else {
    Add-Content -Path $ytConf -Value $line
    Write-Host ("  Cache de yt-dlp -> {0}" -f $CacheDir) -ForegroundColor Green
}

Titulo "=== Listo ==="
Write-Host "  Cierra y vuelve a abrir las terminales para que tomen el nuevo TEMP."
Write-Host "  Revisa la config de ClipForge por rutas con C:\ escritas a mano.`n"
