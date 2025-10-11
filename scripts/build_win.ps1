# Requires: Windows PowerShell 5+ and Python 3.9+
param(
  [string]$Name = "keyboard-com",
  [string]$Version = "0.1.0",
  [string]$Entry = "src/main.py",
  [string]$Python = "",
  # Optional: local path to an OpenRGB portable zip to bundle
  [string]$OpenRGBZip = "",
  # Optional: local path to a folder that contains OpenRGB.exe
  [string]$OpenRGBDir = "",
  [switch]$WithChecksums
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-Python {
  param([string]$Preferred)
  if ($Preferred -and (Test-Path $Preferred)) { return (Resolve-Path $Preferred).Path }
  $candidates = @(
    "python",
    "python3",
    "py -3",
    ".venv/Scripts/python.exe",
    ".venv/bin/python"
  )
  foreach ($c in $candidates) {
    try {
      if ($c -match "\s") {
        & cmd /c $c --version *> $null
      } else {
        & $c --version *> $null
      }
      return $c
    } catch { }
  }
  throw "No Python interpreter found. Install Python 3.9+ first."
}

function Invoke-Py {
  param([string]$Cmd, [string[]]$ArgList)
  if ($Cmd -match "\s") {
    & cmd /c $Cmd @ArgList
  } else {
    & $Cmd @ArgList
  }
}

function New-EmptyDir {
  param([string]$Path)
  if (Test-Path $Path) { Remove-Item -Recurse -Force $Path }
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

$py = Resolve-Python -Preferred $Python
Write-Host "[INFO] Using Python: $py"
Invoke-Py $py @('-V')

Write-Host "[STEP] Create isolated build venv (.build_venv)"
Invoke-Py $py @('-m','venv','.build_venv')
$venvPyCandidates = @('.build_venv/Scripts/python.exe','.build_venv/bin/python.exe','.build_venv/bin/python')
$bpy = $null
foreach ($c in $venvPyCandidates) { if (Test-Path $c) { $bpy = $c; break } }
if (-not $bpy) { throw "Failed to locate venv python under .build_venv" }
Write-Host "[INFO] Build Python: $bpy"
Invoke-Py $bpy @('-V')

Write-Host "[STEP] Install build dependencies"
Invoke-Py $bpy @('-m','ensurepip','--upgrade')
Invoke-Py $bpy @('-m','pip','install','-U','pip','setuptools','wheel','pyinstaller')
Invoke-Py $bpy @('-m','pip','install','-r','requirements.txt')

Write-Host "[STEP] PyInstaller build ($Name)"
New-EmptyDir 'build'
New-EmptyDir 'dist'
Invoke-Py $bpy @('-m','PyInstaller', '--noconfirm','--clean', '--name', $Name, '--paths','src', '--add-data','data;data', $Entry)

$distDir = Join-Path (Get-Location) "dist/$Name"
$exePath = Join-Path $distDir "$Name.exe"
if (!(Test-Path $exePath)) { throw "Build failed: $exePath not found" }

Write-Host "[STEP] Assemble package"
$pkgRoot = Join-Path (Get-Location) "package/$Name"
New-EmptyDir $pkgRoot
Copy-Item -Recurse -Force "$distDir/*" $pkgRoot

if ($OpenRGBZip -and (Test-Path $OpenRGBZip)) {
  Write-Host "[STEP] Bundling OpenRGB from zip: $OpenRGBZip"
  $tmpExtract = Join-Path $env:TEMP ("openrgb_" + [Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force -Path $tmpExtract | Out-Null
  Expand-Archive -Force -Path $OpenRGBZip -DestinationPath $tmpExtract
  $openrgbExe = Get-ChildItem -Path $tmpExtract -Recurse -Filter 'OpenRGB.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $openrgbExe) { throw "OpenRGB.exe not found inside archive." }
  $openrgbDir = Split-Path -Parent $openrgbExe.FullName
  Copy-Item -Recurse -Force $openrgbDir (Join-Path $pkgRoot 'OpenRGB')
  Remove-Item -Recurse -Force $tmpExtract
} elseif ($OpenRGBDir -and (Test-Path $OpenRGBDir)) {
  Write-Host "[STEP] Bundling OpenRGB from folder: $OpenRGBDir"
  $exeCandidate = Join-Path $OpenRGBDir 'OpenRGB.exe'
  if (!(Test-Path $exeCandidate)) {
    $found = Get-ChildItem -Path $OpenRGBDir -Recurse -Filter 'OpenRGB.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) { throw "OpenRGB.exe not found under $OpenRGBDir" } else { $OpenRGBDir = Split-Path -Parent $found.FullName }
  }
  Copy-Item -Recurse -Force $OpenRGBDir (Join-Path $pkgRoot 'OpenRGB')
}

# Write run.ps1
$runPs1 = @'
param(
  [switch]$NoKillOpenRGB
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-PortOpen {
  param([string]$Host, [int]$Port)
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($Host, $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(300)
    if ($ok -and $client.Connected) { $client.Close(); return $true }
    try { $client.Close() } catch {}
    return $false
  } catch { return $false }
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$openrgbExe = Join-Path $here 'OpenRGB/OpenRGB.exe'
$started = $false
$proc = $null
if (Test-Path $openrgbExe) {
  Write-Host "[INFO] Starting bundled OpenRGB server..."
  $proc = Start-Process -FilePath $openrgbExe -ArgumentList '--server' -WindowStyle Minimized -PassThru
  $started = $true
  $deadline = (Get-Date).AddSeconds(10)
  while ((Get-Date) -lt $deadline) {
    if (Test-PortOpen -Host '127.0.0.1' -Port 6742) { break }
    Start-Sleep -Milliseconds 200
  }
}

Write-Host "[INFO] Launching app"
$exe = $env:APP_EXE
if ([string]::IsNullOrWhiteSpace($exe)) { $exe = 'keyboard-com.exe' }
& (Join-Path $here $exe)
$exitCode = $LASTEXITCODE

if ($started -and -not $NoKillOpenRGB) {
  try { Stop-Process -Id $proc.Id -ErrorAction SilentlyContinue } catch {}
}

exit $exitCode
'@
Set-Content -Path (Join-Path $pkgRoot 'run.ps1') -Encoding UTF8 -Value $runPs1

# Write run.bat
$runBat = @"
@echo off
setlocal enabledelayedexpansion
set APP_EXE=keyboard-com.exe
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1"
"@
Set-Content -Path (Join-Path $pkgRoot 'run.bat') -Encoding ASCII -Value $runBat

# Write README
$readme = @'
Keyboard-CPU Demo (Windows) — Offline Package

1) Unzip anywhere (no install required).
2) If OpenRGB is included (OpenRGB\OpenRGB.exe exists), just run run.bat.
   - This will start OpenRGB in server mode automatically and launch the app.
3) If OpenRGB is NOT included, install or unzip OpenRGB yourself and run it with --server.
   - Then run keyboard-com.exe (or run.bat).

Notes
- Admin rights may be needed for OpenRGB to access your keyboard.
- First run may require driver prompts depending on your device.
- Close OpenRGB after use if you launched it manually.
'@
Set-Content -Path (Join-Path $pkgRoot 'README_RUN_EN.txt') -Encoding UTF8 -Value $readme

# Korean quickstart
$readmeKo = @'
키보드 CPU 데모 (Windows) — 오프라인 패키지

1) 압축을 아무 위치에나 풀어주세요(설치 불필요).
2) OpenRGB가 포함되어 있다면(OpenRGB\OpenRGB.exe 존재) run.bat만 실행하면 됩니다.
   - OpenRGB를 서버 모드로 자동 실행한 뒤 앱을 시작합니다.
3) 포함되어 있지 않다면 OpenRGB를 별도로 설치/압축 해제 후 --server 옵션으로 실행하세요.
   - 이후 keyboard-com.exe(또는 run.bat)를 실행합니다.

메모
- 일부 장치에서는 OpenRGB가 키보드에 접근하려면 관리자 권한이 필요할 수 있습니다.
- 첫 실행 시 장치 드라이버 관련 안내가 나올 수 있습니다.
- OpenRGB를 직접 켰다면 사용 후 수동으로 종료하세요.
'@
Set-Content -Path (Join-Path $pkgRoot 'README_RUN_KO.txt') -Encoding UTF8 -Value $readmeKo

Write-Host "[STEP] Create zip"
$zipName = "$Name-$Version-win64.zip"
$zipPath = Join-Path (Get-Location) ("dist/" + $zipName)
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
try {
  $ok = $false
  for ($i=1; $i -le 5; $i++) {
    try {
      Compress-Archive -Path (Join-Path $pkgRoot '*') -DestinationPath $zipPath -Force
      $ok = $true; break
    } catch {
      Write-Warning "Compress-Archive failed (attempt $i): $_"
      Start-Sleep -Milliseconds 900
    }
  }
  if (-not $ok) { throw "Compress-Archive failed after retries" }
  Write-Host "[DONE] Package: $zipPath"
} catch {
  Write-Warning "Compress-Archive failed; trying tar fallback..."
  $tar = Get-Command tar -ErrorAction SilentlyContinue
  if (-not $tar) { throw }
  & $tar.Source -a -c -f $zipPath -C $pkgRoot .
  Write-Host "[DONE] Package (tar): $zipPath"
}

if ($WithChecksums) {
  try {
    Write-Host "[STEP] SHA-256 checksums"
    $h = (Get-FileHash -Algorithm SHA256 -Path $zipPath).Hash
    $sumFile = Join-Path (Get-Location) 'dist/SHA256SUMS.txt'
    ($h + '  ' + $zipName) | Out-File -FilePath $sumFile -Encoding ASCII -Append
    Write-Host "[DONE] Checksums -> $sumFile"
  } catch { Write-Warning "Checksum generation failed: $_" }
}
