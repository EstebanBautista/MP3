# Diseño 2: estático con Pthreads

Simulador paralelo con Pthreads (`eco_pth`): cada hilo atiende una banda fija de filas y los hilos se coordinan con barreras. Incluye también el secuencial (`eco_seq`).

## Compilar

Requiere g++ con Pthreads y OpenMP, CMake, Ninja y Python 3.12. El script fija la ruta del compilador WinLibs de este equipo; en otro equipo, cambie `$bin` en `scripts/build.ps1`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

Los ejecutables quedan en `build/`.

## Ejecutar

El programa lee el mundo de la entrada estándar y escribe el estado final en la salida estándar:

```powershell
Get-Content ecosystem_examples/input5x5 | build/eco_pth.exe --threads 4
```

## Probar

```sh
python -m unittest discover -s tests
```

## Versión final

Esta rama conserva el código tal como quedó al terminar este diseño. La versión final, con los tres diseños, la interfaz web, las mediciones y el informe, está en la rama `main`.
