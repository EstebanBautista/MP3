# Diseño 1: secuencial

Simulador secuencial exacto del ecosistema de conejos, zorros y rocas (`eco_seq`). Es la referencia con la que se comparan los diseños paralelos.

## Compilar

Requiere g++ con Pthreads y OpenMP, CMake, Ninja y Python 3.12. El script fija la ruta del compilador WinLibs de este equipo; en otro equipo, cambie `$bin` en `scripts/build.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

Los ejecutables quedan en `build/`.

## Ejecutar

El programa lee el mundo de la entrada estándar y escribe el estado final en la salida estándar:

```powershell
Get-Content ecosystem_examples/input5x5 | build/eco_seq.exe
```

## Probar

```sh
python -m unittest discover -s tests
```

## Versión final

Esta rama conserva el código tal como quedó al terminar este diseño. La versión final, con los tres diseños, la interfaz web, las mediciones y el informe, está en la rama `main`.
