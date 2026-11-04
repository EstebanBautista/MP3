# Simulación de ecosistema: secuencial, Pthreads y OpenMP

Proyecto del curso 300CIP013 Programación Paralela (2026-II). Simula un ecosistema de conejos, zorros y rocas sobre una matriz, con reglas deterministas, y compara tres diseños que producen exactamente el mismo resultado:

- **Secuencial** (`eco_seq`): referencia exacta.
- **Pthreads estático** (`eco_pth`): bandas de filas fijas.
- **OpenMP adaptativo** (`eco_omp`): bandas que se reparten según el costo de cada fila (`--schedule static` da el reparto fijo).

Además hay una interfaz web local, pruebas automáticas, scripts de medición y el informe (Word y PDF).

## Inicio rápido (paso a paso)

Hay 2 formas. Elija una. La opción A es la más fácil: no necesita instalar compilador.

### Opción A: con Docker (Windows, Mac o Linux)

1. Instale [Docker Desktop](https://www.docker.com/products/docker-desktop/) y ábralo. Espere a que diga "Engine running".
2. Descargue el proyecto:
   ```sh
   git clone https://github.com/EstebanBautista/MP3.git
   cd MP3
   ```
3. Compile y arranque la interfaz web con una sola orden (la primera vez tarda unos minutos):
   ```sh
   docker compose up --build
   ```
4. Abra en el navegador: <http://localhost:8000>
5. Para detenerlo: Ctrl+C en esa terminal (o `docker compose down`).

Para correr los motores o las pruebas dentro de Docker:

```sh
docker compose run --rm ecosistema sh -c "build/eco_seq < ecosystem_examples/input20x20"
docker compose run --rm ecosistema python -m unittest discover -s tests -v
```

### Opción B: en Windows, sin Docker

1. Instale Python 3.12 desde <https://www.python.org/downloads/>. En el instalador marque **"Add python.exe to PATH"**.
2. Instale el compilador (GCC con OpenMP; trae también CMake y Ninja). En PowerShell:
   ```powershell
   winget install --id BrechtSanders.WinLibs.POSIX.UCRT -e
   ```
3. **Cierre PowerShell y ábralo de nuevo** (para que vea el compilador nuevo).
4. Vaya a la carpeta del proyecto y compile:
   ```powershell
   cd C:\ruta\a\la\carpeta\del\proyecto
   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
   ```
   Debe terminar con `Listo. Ejecutables en build\...`. El script busca el compilador solo; si está en otra carpeta, indíquela antes con `$env:ECO_GCC_BIN = "C:\carpeta\de\gcc\bin"`.
5. Arranque la interfaz web:
   ```powershell
   python web\server.py --port 8000
   ```
6. Abra en el navegador: <http://127.0.0.1:8000>. Se detiene con Ctrl+C.

Para los experimentos y sus figuras instale además los paquetes de Python: `python -m pip install -r requirements.txt`.

### Problemas comunes

- **`No se encontró el motor de simulación`** en la página: falta compilar (paso 4 de la opción B).
- **`No se encontro GCC 8 o mas nuevo`**: hay un MinGW viejo o ninguno. Haga los pasos 2 y 3 de la opción B, o use Docker.
- **`running scripts is disabled`**: use la orden completa con `-ExecutionPolicy Bypass`, como arriba.
- **`python` no se reconoce**: reinstale Python marcando "Add python.exe to PATH", o use `py` en lugar de `python`.
- **Puerto 8000 ocupado**: cierre el otro servidor (Ctrl+C o `docker compose down`) o use `--port 8001`.
- **Docker: `failed to connect to the docker API`**: Docker Desktop no está abierto. Ábralo y espere.

### Linux o Mac sin Docker

Necesita g++ 8+, CMake y Ninja (por ejemplo `sudo apt install g++ cmake ninja-build`):

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DECO_STATIC=OFF
cmake --build build
python3 web/server.py --port 8000
```

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

Comparan los tres motores con los casos de la tarea, con 1, 2, 4, 8 y 16 hilos, además de casos límite, la entrada y salida, el servidor web y las mediciones.

## Repetir mediciones y experimentos

Los resultados ya calculados están en `experiments/results/`. Para repetirlos:

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

El informe está en [`docs/report/informe.docx`](docs/report/informe.docx) (Word) y en [`docs/report/informe.pdf`](docs/report/informe.pdf), que es el mismo documento exportado desde Word. Si se edita el Word, vuelva a exportarlo a PDF (Archivo > Exportar > PDF) con el nombre `informe.pdf`.

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
- `docs/report/`: informe en Word y PDF, y sus figuras.
- `ecosystem_examples/`: casos de la tarea.
