<#
.SYNOPSIS
  Find and remove reclaimable disk space left behind by video clipping jobs.

.DESCRIPTION
  DRY RUN BY DEFAULT. Run it with no switches and it only reports what it
  would delete. Nothing is removed until you pass -Execute.

  Deletion is limited to:
    * files under -Root that match known intermediate/source patterns
    * the yt-dlp cache directory
    * *your user* temp folder (files older than -TempOlderThanDays)
  It never touches anything else.

.EXAMPLE
  # 1. Look first — deletes nothing:
  .\cleanup-diskspace.ps1 -Root "C:\Users\17875\Documents\Codex\2026-07-21\you-paste-url-backend-receives-video\clipforge"

.EXAMPLE
  # 2. Then actually delete, keeping every finished clip:
  .\cleanup-diskspace.ps1 -Root "C:\...\clipforge" -Execute

.EXAMPLE
  # 3. Also drop rendered clips from previous batches (they are the output — be sure):
  .\cleanup-diskspace.ps1 -Root "C:\...\clipforge" -Execute -IncludeOldClips
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [switch]$Execute,
    [switch]$IncludeOldClips,
    [int]$TempOlderThanDays = 3
)

$ErrorActionPreference = 'Continue'

function Show-Size([long]$Bytes) {
    if ($Bytes -ge 1GB) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ('{0:N0} MB' -f ($Bytes / 1MB)) }
    return ('{0:N0} KB' -f ($Bytes / 1KB))
}

function Show-Free {
    $d = Get-PSDrive -Name ((Get-Item $Root).PSDrive.Name)
    Write-Host ("  Free on {0}: {1}" -f $d.Name, (Show-Size $d.Free)) -ForegroundColor Cyan
}

if (-not (Test-Path $Root)) { Write-Host "Root not found: $Root" -ForegroundColor Red; exit 1 }
$Root = (Resolve-Path $Root).Path

Write-Host "`n=== Disk before ===" -ForegroundColor White
Show-Free

# ---------------------------------------------------------------- biggest files
Write-Host "`n=== 15 biggest files under Root ===" -ForegroundColor White
Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending | Select-Object -First 15 |
    ForEach-Object {
        Write-Host ("  {0,10}  {1}" -f (Show-Size $_.Length), $_.FullName.Replace($Root, '.'))
    }

# ---------------------------------------------------------------- candidates
$candidates = [System.Collections.Generic.List[object]]::new()

# Partial / aborted downloads and mux leftovers — always safe, never final output.
$partials = Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.part', '.ytdl', '.tmp', '.temp' -or $_.Name -like '*.f[0-9]*.mp4' -or $_.Name -like '*.f[0-9]*.webm' -or $_.Name -like '*.f[0-9]*.m4a' }
foreach ($f in $partials) { $candidates.Add([pscustomobject]@{ Cat = 'partial download'; File = $f }) }

# Pipeline intermediates — regenerable from the source.
$inter = Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.BaseName -match '^(cut|framed|reframed|scaled|trimmed|concat|silence)' -and $_.Extension -in '.mp4', '.webm', '.mkv', '.wav' }
foreach ($f in $inter) { $candidates.Add([pscustomobject]@{ Cat = 'intermediate'; File = $f }) }

# Source downloads — the biggest win, and re-downloadable.
$sources = Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Length -gt 200MB -and $_.Extension -in '.mp4', '.webm', '.mkv', '.m4a' -and
        ($_.DirectoryName -match '(source|download|input|raw|original)' -or $_.BaseName -match '^[A-Za-z0-9_-]{11}$')
    }
foreach ($f in $sources) { $candidates.Add([pscustomobject]@{ Cat = 'source video'; File = $f }) }

# Rendered clips from earlier batches — real output. Opt-in only.
if ($IncludeOldClips) {
    $clips = Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -eq '.mp4' -and ($_.DirectoryName -match '(clip|output|out|render)') -and $_.LastWriteTime -lt (Get-Date).AddDays(-1) }
    foreach ($f in $clips) { $candidates.Add([pscustomobject]@{ Cat = 'old rendered clip'; File = $f }) }
}

# yt-dlp cache — always regenerable.
# LOCALAPPDATA is unset outside Windows, and Join-Path throws on a null Path.
$ytCache = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'yt-dlp' } else { $null }
$cacheBytes = 0
if ($ytCache -and (Test-Path $ytCache)) {
    $cacheBytes = (Get-ChildItem $ytCache -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
}

# Stale temp files owned by this user.
$tempFiles = Get-ChildItem -Path $env:TEMP -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$TempOlderThanDays) }
$tempBytes = ($tempFiles | Measure-Object Length -Sum).Sum

# ---------------------------------------------------------------- report
Write-Host "`n=== Reclaimable ===" -ForegroundColor White
$total = 0
foreach ($g in $candidates | Group-Object Cat) {
    $b = ($g.Group.File | Measure-Object Length -Sum).Sum
    $total += $b
    Write-Host ("  {0,-20} {1,4} files  {2}" -f $g.Name, $g.Count, (Show-Size $b)) -ForegroundColor Yellow
}
if ($cacheBytes -gt 0) { $total += $cacheBytes; Write-Host ("  {0,-20} {1,4}        {2}" -f 'yt-dlp cache', '-', (Show-Size $cacheBytes)) -ForegroundColor Yellow }
if ($tempBytes  -gt 0) { $total += $tempBytes;  Write-Host ("  {0,-20} {1,4} files  {2}" -f "temp >$TempOlderThanDays days", $tempFiles.Count, (Show-Size $tempBytes)) -ForegroundColor Yellow }
Write-Host ("  {0,-20} {1,4}        {2}" -f 'TOTAL', '', (Show-Size $total)) -ForegroundColor Green

if (-not $IncludeOldClips) {
    Write-Host "`n  (Rendered clips kept. Add -IncludeOldClips to reclaim those too.)" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- delete
if (-not $Execute) {
    Write-Host "`nDRY RUN — nothing deleted. Re-run with -Execute to remove the above.`n" -ForegroundColor Cyan
    exit 0
}

Write-Host "`n=== Deleting ===" -ForegroundColor Red
$freed = 0; $errors = 0
foreach ($c in $candidates) {
    try {
        $sz = $c.File.Length
        Remove-Item -LiteralPath $c.File.FullName -Force -ErrorAction Stop
        $freed += $sz
    } catch { $errors++; Write-Host ("  skip (in use): {0}" -f $c.File.Name) -ForegroundColor DarkGray }
}
if ($ytCache -and (Test-Path $ytCache)) {
    try { Remove-Item -LiteralPath $ytCache -Recurse -Force -ErrorAction Stop; $freed += $cacheBytes } catch { $errors++ }
}
foreach ($t in $tempFiles) {
    try { $sz = $t.Length; Remove-Item -LiteralPath $t.FullName -Force -ErrorAction Stop; $freed += $sz } catch { $errors++ }
}

Write-Host ("`n  Freed {0}  ({1} files skipped, usually still open)" -f (Show-Size $freed), $errors) -ForegroundColor Green
Write-Host "`n=== Disk after ===" -ForegroundColor White
Show-Free
Write-Host "`nRestart ClipForge, then retry the video.`n" -ForegroundColor Cyan
