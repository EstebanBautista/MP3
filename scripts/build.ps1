# Configures and builds all engine executables into build/.
$ErrorActionPreference = 'Stop'
$bin = 'C:\Users\ESTEBAN\AppData\Local\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin'
$env:PATH = "$bin;$env:PATH"
Set-Location (Split-Path -Parent $PSScriptRoot)

& cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_CXX_COMPILER=$bin\g++.exe" "-DCMAKE_MAKE_PROGRAM=$bin\ninja.exe"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& cmake --build build
exit $LASTEXITCODE
