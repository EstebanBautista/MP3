# Resumen de rendimiento (hechos medidos)

Todos los tiempos salen de `performance.csv`, `performance_linux.csv` y `barriers.csv`, sin editar a mano.
Mediana de 7 repeticiones (Windows) o 3 (Linux); entre corchetes el rango intercuartil (IQR), en segundos.
`xS` = aceleración respecto a `eco_seq` en el mismo caso (T_seq / T), `eE` = eficiencia (S / hilos).
Cada medición comprobó que su salida coincide con la esperada (archivo `output*`, o la salida de `eco_seq` para el mundo grande); ninguna falló.

## Condiciones

- Windows 10 nativo, i7-10700F (8 núcleos físicos, 16 lógicos con SMT), 32 GB, plan de energía "Plus-Ultra", g++ 16.2.0 (WinLibs UCRT), `-O3`, enlazado estático. Carga de CPU antes de la corrida: 0 % (ver `environment.txt`). Docker Desktop estaba en ejecución en segundo plano (sin contenedores en marcha durante la medición de Windows).
- 672 mediciones entre 16:09:27 y 16:33:14 (unos 24 min), orden alternado (directo en repeticiones impares, inverso en pares). Hay una marca de tiempo por medición en el CSV.
- Mundo grande: `tools/worldgen.py`, semilla 20261031, 1000x1000, 25000 conejos, 5000 zorros, 5000 rocas (las densidades de `input200x200`, por 25), parámetros 3 20 10, 1000 generaciones. Se regenera con `python experiments/measure.py gen-large`; no está en git. No hay salida esperada: todos los diseños e hilos se compararon byte a byte con la salida de `eco_seq`.
- Linux: contenedor `gcc:14` (GCC 14.4.0) sobre Docker Desktop/WSL2 en la misma máquina. **No es Linux nativo** y no se mezcla con las cifras de Windows. 3 repeticiones, solo `200x200` y el mundo grande.
- Resolución del tiempo de CPU en Windows: unos 15,6 ms. En `20x20` (5 ms de reloj) el CPU medido no es fiable.

## Hallazgos

1. **Sobrecoste a 1 hilo.** Con 1 hilo, `eco_pth` y `eco_omp` son más lentos que `eco_seq` en todos los casos: entre +16 % y +21 % de 100x100 a 1000x1000 (por ejemplo 1000x1000: 8,688 s frente a 10,227 s Pthreads, 10,312 s OpenMP adaptativo, 10,252 s estático), y +30 % a +33 % en 20x20. Es estable (IQR menor de 0,16 s) y no es ruido. En Linux (contenedor) es +21 % a +24 %. No se investigó la causa; no se afirma ninguna.
2. **Mundos pequeños y medianos: el paralelismo no compensa en Windows.** En 20x20 todos los diseños son más lentos que el secuencial con 2 o más hilos (a 16 hilos 0,260 s Pthreads y unos 0,38 s OpenMP, frente a 0,004 s). En 100x100 el mejor resultado es Pthreads con 4 hilos: 0,630 s, x1,66; OpenMP no pasa de x0,96 (4 hilos) y baja a x0,28 con 16. Los dos casos desequilibrados 100x100 dan resultado parecido: OpenMP queda por debajo de 1 en todos los hilos.
3. **200x200.** Mejor Pthreads con 8 hilos, 1,481 s (x2,70, e0,34); OpenMP adaptativo mejor con 4 hilos, 2,071 s (x1,93). Con 16 hilos empeoran los tres (x1,79 Pthreads, x1,18 OpenMP).
4. **Mundo grande (el cómputo domina).** Es el único caso con aceleración clara: Pthreads x2,73 con 4 hilos, x4,14 con 8, x4,27 con 16; OpenMP adaptativo x2,80, x3,94, x4,14; OpenMP estático x2,75, x3,71, x4,09. La eficiencia a 8 hilos es 0,46 a 0,52. Pasar de 8 a 16 hilos (SMT) casi no mejora (2,098 s a 2,032 s en Pthreads; las diferencias están en el orden del IQR, 0,04 a 0,18 s). El tiempo de CPU total sube de 10,3 s (1 hilo) a unos 15 s (8 hilos) y 26 s (16 hilos), es decir, con más hilos se consume más CPU para el mismo trabajo.
5. **Coste de barrera (microbenchmark, `barriers.csv`, 40 000 barreras vacías, 7 repeticiones; medianas, mín–máx casi iguales).** OpenMP: 12,8 µs (2 hilos), 24,1 (4), 47,9 (8), 92,9 (16). Pthreads: 4,3, 6,9, 25,3, 66,6. Coincide con lo observado (unos 47 µs OpenMP y 25 µs Pthreads a 8 hilos). Pthreads es más barato que OpenMP en cada tamaño. A 16 hilos, 100x100 tarda 3,70 s (OpenMP adaptativo) y 2,26 s (Pthreads) en 10 000 generaciones, es decir, unos 370 µs y 226 µs por generación, cifras del mismo orden que unas pocas barreras por generación a 93 y 67 µs; el número exacto de barreras por generación no se contó en esta tarea, así que esto es una comparación de órdenes de magnitud, no una atribución demostrada.
6. **Resultado contrario a lo esperado: el reparto adaptativo no reduce el tiempo.** El desequilibrio medido (máx/media) es menor en adaptativo que en estático en los casos con 2 o más hilos (por ejemplo `100x100_unbal01` a 16 hilos: 1,020 frente a 1,087; 1000x1000 a 8 hilos: 1,011 frente a 1,053), pero el tiempo total no mejora de forma apreciable: 1000x1000 a 8 hilos, 2,203 s [0,104] adaptativo frente a 2,340 s [0,158] estático (diferencia del orden del IQR). Los valores de desequilibrio son pequeños (estático entre 1,02 y 1,09). Con estos datos no se observa una ventaja de tiempo del modo adaptativo; no se aisló la causa.
7. **Linux (contenedor/WSL2) contradice a Windows en OpenMP frente a Pthreads.** En 200x200 con 16 hilos: OpenMP adaptativo 0,748 s (x5,35), estático 0,715 s (x5,59), Pthreads 6,835 s (x0,59). En Windows el mismo caso daba Pthreads 2,230 s y OpenMP 3,393 s. En el mundo grande Linux da x3,87 (Pthreads), x4,08 (OpenMP adaptativo) y x4,10 (estático) a 16 hilos, parecido a Windows. Las medianas de Linux usan solo 3 repeticiones; algunos IQR son grandes (OpenMP adaptativo a 16 hilos en el mundo grande: 0,407 s).
8. **SMT.** En Windows, 16 hilos es más lento que 8 en todos los casos excepto el mundo grande, donde hay empate dentro del IQR. En Linux (contenedor) 16 hilos mejora a 8 en OpenMP 200x200 (0,935 s a 0,748 s adaptativo) y apenas en el mundo grande; en Pthreads 16 hilos es peor.

## Anomalías y límites

- Las mayores dispersiones entre mínimo y máximo de una celda (con tiempo mayor de 0,05 s) son de 1,29 (Pthreads, `100x100_unbal02`, 8 hilos) y 1,21 (OpenMP estático, mundo grande, 16 hilos). Todas las repeticiones permanecen en el CSV.
- El IQR de OpenMP estático en 200x200 a 8 y 16 hilos es 0,177 y 0,199 s, relativamente alto.
- No se midió Linux nativo. El contenedor comparte la máquina con Windows; las cifras de Linux no deben tomarse como Linux nativo.
- Las cifras de CPU de Windows tienen resolución de unos 15,6 ms.
- Las gráficas usan la aceleración respecto a `eco_seq` (no respecto al mismo diseño con 1 hilo), de modo que el sobrecoste a 1 hilo queda visible. La función `summarize` también da la aceleración respecto al mismo diseño con 1 hilo (en `measure.py summary`).

## Figuras

`docs/report/figuras/perf_aceleracion.png`, `perf_eficiencia.png`, `perf_tiempo_cpu.png`, `perf_desequilibrio.png`, `perf_barreras.png`, y `perf_aceleracion_linux.png` (contenedor Linux).

## Tablas completas (Windows nativo)

Celdas: mediana [IQR] en segundos, aceleración respecto a `eco_seq`, eficiencia. La última columna es el sobrecoste del diseño con 1 hilo sobre `eco_seq`.

### 100x100 (eco_seq: 1.043 s, IQR 0.011, n=7)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 1.211 [0.006] x0.86 e0.86 | 0.861 [0.006] x1.21 e0.61 | 0.630 [0.031] x1.66 e0.41 | 0.916 [0.060] x1.14 e0.14 | 2.260 [0.003] x0.46 e0.03 | +16.1 % |
| OpenMP adaptativo | 1.229 [0.016] x0.85 e0.85 | 1.106 [0.009] x0.94 e0.47 | 1.100 [0.012] x0.95 e0.24 | 1.756 [0.042] x0.59 e0.07 | 3.703 [0.007] x0.28 e0.02 | +17.9 % |
| OpenMP estatico | 1.223 [0.006] x0.85 e0.85 | 1.111 [0.018] x0.94 e0.47 | 1.090 [0.005] x0.96 e0.24 | 1.789 [0.044] x0.58 e0.07 | 3.709 [0.068] x0.28 e0.02 | +17.3 % |

### 100x100_unbal01 (eco_seq: 0.746 s, IQR 0.008, n=7)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 0.897 [0.005] x0.83 e0.83 | 0.698 [0.002] x1.07 e0.53 | 0.559 [0.007] x1.33 e0.33 | 0.873 [0.004] x0.85 e0.11 | 2.339 [0.061] x0.32 e0.02 | +20.3 % |
| OpenMP adaptativo | 0.904 [0.010] x0.83 e0.83 | 0.946 [0.013] x0.79 e0.39 | 1.013 [0.007] x0.74 e0.18 | 1.806 [0.034] x0.41 e0.05 | 3.755 [0.032] x0.20 e0.01 | +21.2 % |
| OpenMP estatico | 0.901 [0.007] x0.83 e0.83 | 0.949 [0.011] x0.79 e0.39 | 1.006 [0.006] x0.74 e0.19 | 1.772 [0.012] x0.42 e0.05 | 3.715 [0.042] x0.20 e0.01 | +20.8 % |

### 100x100_unbal02 (eco_seq: 1.019 s, IQR 0.012, n=7)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 1.203 [0.017] x0.85 e0.85 | 0.863 [0.003] x1.18 e0.59 | 0.652 [0.024] x1.56 e0.39 | 0.974 [0.076] x1.05 e0.13 | 2.321 [0.050] x0.44 e0.03 | +18.0 % |
| OpenMP adaptativo | 1.213 [0.017] x0.84 e0.84 | 1.109 [0.006] x0.92 e0.46 | 1.101 [0.007] x0.93 e0.23 | 1.768 [0.036] x0.58 e0.07 | 3.736 [0.105] x0.27 e0.02 | +18.9 % |
| OpenMP estatico | 1.214 [0.007] x0.84 e0.84 | 1.116 [0.012] x0.91 e0.46 | 1.088 [0.009] x0.94 e0.23 | 1.739 [0.028] x0.59 e0.07 | 3.705 [0.041] x0.28 e0.02 | +19.0 % |

### 200x200 (eco_seq: 3.999 s, IQR 0.015, n=7)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 4.673 [0.025] x0.86 e0.86 | 2.716 [0.013] x1.47 e0.74 | 1.663 [0.097] x2.41 e0.60 | 1.481 [0.093] x2.70 e0.34 | 2.230 [0.032] x1.79 e0.11 | +16.8 % |
| OpenMP adaptativo | 4.682 [0.025] x0.85 e0.85 | 2.942 [0.008] x1.36 e0.68 | 2.071 [0.048] x1.93 e0.48 | 2.110 [0.070] x1.90 e0.24 | 3.393 [0.122] x1.18 e0.07 | +17.1 % |
| OpenMP estatico | 4.686 [0.016] x0.85 e0.85 | 2.981 [0.045] x1.34 e0.67 | 2.061 [0.036] x1.94 e0.49 | 2.239 [0.177] x1.79 e0.22 | 3.384 [0.199] x1.18 e0.07 | +17.2 % |

### 20x20 (eco_seq: 0.004 s, IQR 0.000, n=7)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 0.005 [0.000] x0.77 e0.77 | 0.022 [0.001] x0.18 e0.09 | 0.031 [0.001] x0.13 e0.03 | 0.095 [0.001] x0.04 e0.01 | 0.260 [0.002] x0.01 e0.00 | +30.3 % |
| OpenMP adaptativo | 0.005 [0.000] x0.75 e0.75 | 0.051 [0.001] x0.08 e0.04 | 0.098 [0.001] x0.04 e0.01 | 0.197 [0.001] x0.02 e0.00 | 0.382 [0.002] x0.01 e0.00 | +32.5 % |
| OpenMP estatico | 0.005 [0.000] x0.75 e0.75 | 0.051 [0.000] x0.08 e0.04 | 0.097 [0.001] x0.04 e0.01 | 0.195 [0.001] x0.02 e0.00 | 0.379 [0.002] x0.01 e0.00 | +33.2 % |

### large1000x1000 (eco_seq: 8.688 s, IQR 0.155, n=7)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 10.227 [0.014] x0.85 e0.85 | 5.469 [0.080] x1.59 e0.79 | 3.184 [0.167] x2.73 e0.68 | 2.098 [0.090] x4.14 e0.52 | 2.032 [0.043] x4.27 e0.27 | +17.7 % |
| OpenMP adaptativo | 10.312 [0.142] x0.84 e0.84 | 5.402 [0.026] x1.61 e0.80 | 3.102 [0.124] x2.80 e0.70 | 2.203 [0.104] x3.94 e0.49 | 2.097 [0.151] x4.14 e0.26 | +18.7 % |
| OpenMP estatico | 10.252 [0.076] x0.85 e0.85 | 5.442 [0.148] x1.60 e0.80 | 3.158 [0.040] x2.75 e0.69 | 2.340 [0.158] x3.71 e0.46 | 2.123 [0.184] x4.09 e0.26 | +18.0 % |


## Tablas completas (Linux, contenedor en WSL2, 3 repeticiones)

### 200x200 (eco_seq: 4.000 s, IQR 0.045, n=3)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 4.967 [0.054] x0.81 e0.81 | 3.377 [0.014] x1.18 e0.59 | 3.322 [0.040] x1.20 e0.30 | 4.171 [0.115] x0.96 e0.12 | 6.835 [0.097] x0.59 e0.04 | +24.2 % |
| OpenMP adaptativo | 4.888 [0.015] x0.82 e0.82 | 2.776 [0.060] x1.44 e0.72 | 1.686 [0.148] x2.37 e0.59 | 0.935 [0.011] x4.28 e0.53 | 0.748 [0.117] x5.35 e0.33 | +22.2 % |
| OpenMP estatico | 4.875 [0.022] x0.82 e0.82 | 2.737 [0.011] x1.46 e0.73 | 1.655 [0.035] x2.42 e0.60 | 0.973 [0.070] x4.11 e0.51 | 0.715 [0.080] x5.59 e0.35 | +21.9 % |

### large1000x1000 (eco_seq: 9.797 s, IQR 0.110, n=3)

| Diseno | 1 hilos | 2 hilos | 4 hilos | 8 hilos | 16 hilos | Sobrecoste a 1 hilo |
|---|---|---|---|---|---|---|
| Pthreads | 11.812 [0.242] x0.83 e0.83 | 5.849 [0.110] x1.67 e0.84 | 3.680 [0.026] x2.66 e0.67 | 2.622 [0.063] x3.74 e0.47 | 2.528 [0.131] x3.87 e0.24 | +20.6 % |
| OpenMP adaptativo | 11.856 [0.042] x0.83 e0.83 | 6.284 [0.127] x1.56 e0.78 | 3.744 [0.038] x2.62 e0.65 | 2.585 [0.037] x3.79 e0.47 | 2.399 [0.407] x4.08 e0.26 | +21.0 % |
| OpenMP estatico | 11.891 [0.046] x0.82 e0.82 | 6.155 [0.036] x1.59 e0.80 | 3.736 [0.059] x2.62 e0.66 | 2.525 [0.086] x3.88 e0.49 | 2.389 [0.131] x4.10 e0.26 | +21.4 % |

