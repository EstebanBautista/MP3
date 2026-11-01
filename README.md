# Simulación de ecosistema: secuencial, Pthreads y OpenMP

Proyecto del curso 300CIP013 Programación Paralela (2026-II). Simula un ecosistema de conejos, zorros y rocas sobre una matriz, con reglas deterministas, y compara tres diseños que producen exactamente el mismo resultado:

- **Secuencial** (`eco_seq`): referencia exacta.
- **Pthreads estático** (`eco_pth`): bandas de filas fijas.
- **OpenMP adaptativo** (`eco_omp`): bandas que se reparten según el costo de cada fila (`--schedule static` da el reparto fijo).

Además hay una interfaz web local, pruebas automáticas, scripts de medición y un informe en PDF.

## Requisitos

- GCC con OpenMP, por ejemplo WinLibs 16.2 en Windows.
- CMake.
- Ninja.
- Python 3.12.
- Los paquetes de `requirements.txt` (`python -m pip install -r requirements.txt`): pypdf, numpy, reportlab y matplotlib. Los usan las pruebas, los scripts de experimentos y el informe.
- Docker, solo para `scripts/tsan.sh` (ThreadSanitizer).

Los motores y la interfaz web solo necesitan Python y el compilador. Node es opcional: sin él se omiten las pruebas de `tests/test_web_restart.py`.

## Compilar

En Windows, con PowerShell, desde la carpeta del proyecto:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

`scripts/build.ps1` tiene fija la ruta del compilador de la máquina donde se desarrolló (la variable `$bin`, que apunta a la carpeta `mingw64\bin` de WinLibs instalado con winget). En otra máquina, edite esa línea y ponga la carpeta `bin` de su GCC, que debe contener `g++.exe` y `ninja.exe`. Si `g++`, `cmake` y `ninja` ya están en el `PATH`, también sirve compilar a mano:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

En Linux, si solo existe `libgomp` dinámica, agregue `-DECO_STATIC=OFF` a la primera orden.

Los ejecutables quedan en `build/`: `eco_seq`, `eco_pth`, `eco_omp` (con `.exe` en Windows), además de `rules_test` y `omp_bands_test`, que usan las pruebas.

## Ejecutar los motores

Cada motor lee el mundo inicial por la entrada estándar y escribe el mundo final por la salida estándar. En la salida de error imprime una línea con el tiempo y el desequilibrio de carga. Opciones:

- `--threads N`: número de hilos (1 por defecto; `eco_seq` siempre usa uno).
- `--dump-all`: escribe el mundo de todas las generaciones, como los archivos `allgen*`.
- `--frames`: escribe cuadros binarios para la interfaz web (no se combina con `--dump-all`).
- `--stats-file RUTA`: guarda estadísticas de la corrida.
- `--schedule adaptive|static`: solo en `eco_omp`.

Los mundos de ejemplo están en `ecosystem_examples/` (`input*` es la entrada, `output*` el resultado esperado).

PowerShell (use `cmd /c` para que la redirección envíe los bytes sin cambios):

```powershell
cmd /c "build\eco_seq.exe < ecosystem_examples\input20x20 > salida.txt"
cmd /c "build\eco_pth.exe --threads 4 < ecosystem_examples\input200x200 > salida.txt"
cmd /c "build\eco_omp.exe --threads 8 --schedule adaptive < ecosystem_examples\input100x100_unbal01 > salida.txt"
```

Git Bash o Linux:

```sh
build/eco_seq < ecosystem_examples/input20x20 > salida.txt
build/eco_pth --threads 4 < ecosystem_examples/input200x200 > salida.txt
build/eco_omp --threads 8 --schedule adaptive < ecosystem_examples/input100x100_unbal01 > salida.txt
```

## Interfaz web

```sh
python web/server.py --port 8000
```

Abra `http://127.0.0.1:8000` en el navegador. Permite elegir un caso, generar un mundo aleatorio, iniciar, pausar, cambiar la velocidad y ver los contadores y la gráfica de población. Usa el motor `build/eco_seq`, así que hay que compilar antes. Se detiene con Ctrl+C.

## Pruebas

Desde la carpeta del proyecto, después de compilar:

```sh
python -m unittest discover -s tests -v
```

La suite tiene 239 pruebas. Comparan los tres motores con los casos de la tarea, con 1, 2, 4, 8 y 16 hilos, además de casos límite, la entrada y salida, el servidor web, las mediciones y el informe. No se incluye `ecosystem_examples/allgen100x100` (300 MB, se excluye del repositorio); ninguna prueba lo necesita. Si se agrega, la herramienta `tools/diff_allgen.py` compara dos archivos `allgen`.

## Repetir mediciones y experimentos

Las mediciones de tiempo y los experimentos de dinámica de población son reproducibles. Los resultados ya calculados están en `experiments/results/`.

```sh
python experiments/measure.py env --out mi_entorno.txt      # describe el equipo y el compilador
python experiments/measure.py gen-large                     # genera el mundo grande (no se guarda en git)
python experiments/measure.py run --csv mis_tiempos.csv     # mide; reanuda si se interrumpe
python experiments/measure.py summary --csv mis_tiempos.csv # tabla: mediana, rango intercuartil, aceleración, eficiencia
python experiments/plot_performance.py            # figuras de rendimiento
python experiments/ecosystem_runs.py run          # experimentos de población con eco_seq
python experiments/ecosystem_runs.py plot         # figuras de población
```

Use siempre rutas nuevas en `--csv` y `--out`. Sin `--csv`, `measure.py run` toma `experiments/results/performance.csv`, ve las filas ya guardadas y no mide nada; sin `--out`, `measure.py env` sobrescribe `experiments/results/environment.txt`. `measure.py run` también acepta `--reps`, `--cases` y `--threads`; consulte `--help` de cada subcomando. Una medición completa tarda; los tiempos dependen del equipo. `measure.py run` se detiene si alguna salida difiere del caso esperado.

ThreadSanitizer (necesita Docker; el encabezado de `scripts/tsan.sh` trae la orden exacta):

```sh
docker run --rm --security-opt seccomp=unconfined -e TSAN_IMAGE=gcc:14 -v "$PWD:/src" -w /src gcc:14 bash scripts/tsan.sh
```

## Informe

El informe está en [`docs/report/informe.pdf`](docs/report/informe.pdf) (fuente: [`docs/report/informe.md`](docs/report/informe.md)). Los valores medidos del texto se leen de `experiments/results/` al generarlo.

Para regenerarlo:

```sh
python docs/report/build_report.py
```

La generación lee el tamaño de los diseños desde las ramas `diseno-*` o `origin/diseno-*`. Por eso falla desde un ZIP o desde un clon de una sola rama: hace falta un clon con esas ramas.

Antes de la entrega, abra `docs/report/build_report.py` y edite las dos constantes del inicio:

- `TEAM = ["[NOMBRE INTEGRANTE 1]", "[NOMBRE INTEGRANTE 2]"]`: reemplace cada texto con el nombre de un integrante.
- `VIDEO_URL = "[ENLACE VIDEO]"`: reemplace con el enlace del video.

Luego ejecute de nuevo la orden y revise el PDF.

## Ramas

- `main`: versión final de entrega.
- `desarrollo`: desarrollo integrado de los tres diseños, la interfaz, las pruebas, las mediciones y el informe.
- `diseno-1-secuencial`: el simulador secuencial exacto.
- `diseno-2-estatico`: el diseño con Pthreads y reparto estático.
- `diseno-3-adaptativo`: el diseño con OpenMP y reparto adaptativo.

## Estructura

- `engine/`: motores y código común (mundo, entrada y salida, línea de comandos).
- `web/`: servidor e interfaz.
- `tests/`: pruebas en Python y en C++.
- `experiments/`: mediciones, experimentos y resultados.
- `tools/`: generador de mundos y comparador de archivos `allgen`.
- `docs/`: informe.
- `ecosystem_examples/`: casos de la tarea.
