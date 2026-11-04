# Compiles the engines into build\ on Windows.
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
# Finds GCC by itself: first $env:ECO_GCC_BIN, then WinLibs installed with winget, then g++ in PATH.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    Write-Host ""
    Write-Host "Solucion 1 (recomendada en Windows): instale el compilador con este comando y luego CIERRE y vuelva a abrir PowerShell:"
    Write-Host "    winget install --id BrechtSanders.WinLibs.POSIX.UCRT -e"
    Write-Host "Solucion 2: use Docker (no necesita compilador): docker compose up --build"
    exit 1
}

function Get-GccMajor($gpp) {
    try { return [int]((& $gpp -dumpversion) -split '\.')[0] } catch { return 0 }
}

# 1. Candidate folders that contain g++.exe.
$candidates = @()
if ($env:ECO_GCC_BIN) { $candidates += $env:ECO_GCC_BIN }
$winget = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
if (Test-Path $winget) {
    Get-ChildItem $winget -Directory -Filter 'BrechtSanders.WinLibs*' -ErrorAction SilentlyContinue | ForEach-Object {
        $candidates += (Join-Path $_.FullName 'mingw64\bin')
    }
}
foreach ($dir in @('C:\mingw64\bin', 'C:\msys64\ucrt64\bin', 'C:\msys64\mingw64\bin')) { $candidates += $dir }
$inPath = Get-Command g++ -ErrorAction SilentlyContinue
if ($inPath) { $candidates += (Split-Path $inPath.Source) }

# 2. The first one with GCC 8 or newer (C++17 and OpenMP). Old MinGW 6.x does not work.
$bin = $null
foreach ($dir in $candidates) {
    $gpp = Join-Path $dir 'g++.exe'
    if ((Test-Path $gpp) -and ((Get-GccMajor $gpp) -ge 8)) { $bin = $dir; break }
}
if (-not $bin) { Fail "No se encontro GCC 8 o mas nuevo (g++.exe)." }
$env:PATH = "$bin;$env:PATH"
$gpp = Join-Path $bin 'g++.exe'
Write-Host "Compilador: $gpp (GCC $(& $gpp -dumpversion))"

# 3. CMake and a build tool. WinLibs includes both cmake and ninja.
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) { Fail "No se encontro cmake." }
$ninja = Get-Command ninja -ErrorAction SilentlyContinue
$make = Get-Command mingw32-make -ErrorAction SilentlyContinue
if ($ninja) {
    $gen = @('-G', 'Ninja', "-DCMAKE_MAKE_PROGRAM=$($ninja.Source)")
} elseif ($make) {
    $gen = @('-G', 'MinGW Makefiles', "-DCMAKE_MAKE_PROGRAM=$($make.Source)")
} else {
    Fail "No se encontro ninja ni mingw32-make."
}

# 4. A build\ folder configured on another machine or with another compiler breaks cmake: start clean.
$cache = 'build\CMakeCache.txt'
if ((Test-Path $cache) -and -not (Select-String -Path $cache -SimpleMatch -Quiet -Pattern $gpp.Replace('\', '/'))) {
    Write-Host "Borrando build\ porque se configuro con otro compilador."
    Remove-Item -Recurse -Force build
}

& cmake -S . -B build @gen -DCMAKE_BUILD_TYPE=Release "-DCMAKE_CXX_COMPILER=$gpp"
if ($LASTEXITCODE -ne 0) { Fail "cmake no pudo configurar el proyecto." }
& cmake --build build
if ($LASTEXITCODE -ne 0) { Fail "La compilacion fallo." }
Write-Host ""
Write-Host "Listo. Ejecutables en build\: eco_seq.exe, eco_pth.exe, eco_omp.exe" -ForegroundColor Green
Write-Host "Interfaz web: python web\server.py --port 8000   y abra http://127.0.0.1:8000"
