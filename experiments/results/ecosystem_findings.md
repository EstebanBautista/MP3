# Hallazgos de los experimentos del ecosistema

Datos para quien redacte el informe. Todo lo de esta página sale de `experiments/results/ecosystem_summary.csv`
(45 corridas) y de las series en `experiments/results/ecosystem/`. Se reproduce con
`python experiments/ecosystem_runs.py run` y `python experiments/ecosystem_runs.py plot`.
Cuando algo es una hipótesis no probada, se dice así.

## Resultado principal

**No se observaron ciclos depredador-presa lentos y claros en ninguna configuración.** Con el umbral
declarado (autocorrelación >= 0,3), 38 de las 39 corridas de los barridos (10 000 generaciones) no tienen ciclo
lento ni en conejos ni en zorros. La única excepción es débil (ver "Ciclo débil" más abajo). Lo que sí se
ve en todas las configuraciones con coexistencia es una oscilación **rápida** con periodo igual a
`GEN_PROC + 1` de cada especie (la banda gruesa de las gráficas). Las poblaciones que coexisten se
estabilizan en un nivel casi constante tras un transitorio inicial (en las curvas, de unas pocas centenas de
generaciones; con 0 % de rocas y con `GEN_PROC_FOXES`=40 los zorros siguen derivando durante unas 4000), con
fluctuaciones irregulares pequeñas. No hay desfase conejo-zorro medible: `fox_lag` es `None` en todos los
barridos, porque requiere ciclo lento en ambas especies.

## Método

- Mundo 100x100, motor `build/eco_seq.exe` con `--stats-file`, 10 000 generaciones, semillas 1, 2 y 3
  (la semilla controla la posición inicial de animales y rocas).
- **Configuración base** (elegida una sola vez, antes de los barridos, con una exploración pequeña: 10
  combinaciones de conejos 700 a 3000 y zorros 70 a 300, 3000 generaciones, semilla 1; en todas
  coexistieron ambas especies, y no se ajustó nada después):
  1500 conejos (15 %), 150 zorros (1,5 %), 500 rocas (5 %), `GEN_PROC_RABBITS`=3, `GEN_PROC_FOXES`=20,
  `GEN_FOOD_FOXES`=10 (los valores de los ejemplos de la tarea).
- Barridos, un parámetro a la vez desde la base (13 configuraciones x 3 semillas = 39 corridas):
  `GEN_PROC_RABBITS` en {2, 3, 5, 8}; `GEN_PROC_FOXES` en {5, 10, 20, 40}; `GEN_FOOD_FOXES` en {3, 6, 10, 20};
  rocas 0, 5, 15, 30 % (0, 500, 1500, 3000 rocas). Los valores de los barridos se fijaron antes de correr.
- Corridas largas adicionales (20 000 generaciones, mismas semillas, 6 corridas): la base y `GEN_PROC_FOXES`=10,
  porque esta última mostró una señal débil a 10 000.
- Análisis (`analyze`): se descarta el primer 20 % de la serie (transitorio) y la tendencia lineal. El
  **periodo crudo** es el primer pico de autocorrelación >= 0,3 de la serie cruda (corresponde a la oscilación
  rápida, si existe). Los periodos rápidos (<= 50 generaciones) se eliminan con una media móvil cuya
  ventana es el mínimo común múltiplo de ellos (84 en la base; tope 200). El **periodo lento** es el
  pico de autocorrelación de la serie suavizada, que debe ser >= **0,3** y venir precedido de autocorrelación
  negativa; si no, es `None`. Se busca hasta un tercio de la serie (al menos 3 repeticiones). Limitación: la
  media móvil impide ver ciclos más cortos que su ventana (por ejemplo, menos de 84 generaciones en la base).
- Las pruebas (`tests/test_ecosystem.py`) usan señales sintéticas, incluida una senoide lenta (periodo 1000)
  más una rápida (periodo 10): se recuperan ambas y el desfase.
- Los CSV crudos pesan unos 125 KB (10 000 generaciones) o 250 KB (20 000); ninguno pasa de 500 KB, así que no se
  comprimieron ni se diezmaron.

## La oscilación rápida

Periodos de la serie cruda (`rabbit_raw_period`, `fox_raw_period`), constantes entre semillas:

| Parámetro | Periodo crudo de conejos | Periodo crudo de zorros |
|---|---|---|
| `GEN_PROC_RABBITS`=2 (`GEN_PROC_FOXES`=20) | 3 | 21 |
| `GEN_PROC_RABBITS`=3 (base) | 4 | 21 |
| `GEN_PROC_RABBITS`=5 | 6 | 21 |
| `GEN_PROC_FOXES`=10 | 4 | 11 |
| `GEN_PROC_FOXES`=40 | 4 | 41 |

El periodo de cada especie coincide con su `GEN_PROC + 1` en todas las corridas con coexistencia. Es lo que
se observa; no se probó el mecanismo (la hipótesis de que lo causan los periodos de reproducción fijos junto con
la regla de selección `(G+X+Y) mod P` queda sin verificar).

Tamaño de la banda (base, semilla 1, tras el transitorio): coeficiente de variación de la serie cruda 0,23
(conejos) y 0,21 (zorros); tras quitar los periodos cortos, 0,032 y 0,026. En 100 generaciones (figura
`eco_base_serie.png`) los conejos van de unos 1250 a 2700 y los zorros hacen dientes de sierra de 21
generaciones entre unos 300 y 680. La banda es, por tanto, 7 a 8 veces más ancha que la variación lenta.

## Resultados por parámetro (media de la ventana posterior al transitorio, 3 semillas)

| Configuración | Coexisten (de 3) | Conejos | Zorros | Amplitud relativa lenta (zorros) |
|---|---|---|---|---|
| Base (5 % rocas, 3/20/10) | 3 | 1684 / 1830 / 1768 | 508 / 472 / 486 | 0,026 a 0,064 |
| `GEN_PROC_RABBITS`=2 | 3 | 1828 a 1836 | 677 a 682 | 0,023 a 0,025 |
| `GEN_PROC_RABBITS`=5 | 3 | 2572 a 2655 | 27 a 52 | 0,18 a 0,22 |
| `GEN_PROC_RABBITS`=8 | 0 | 1795 a 1870 | 0 a 4 | - |
| `GEN_PROC_FOXES`=5 | 0 | 0 | 126 a 152 | - |
| `GEN_PROC_FOXES`=10 | 3 | 935 a 950 | 653 a 655 | 0,033 a 0,040 |
| `GEN_PROC_FOXES`=40 | 3 | 3319 a 3489 | 84 a 110 | 0,31 a 0,45 |
| `GEN_FOOD_FOXES`=3 | 0 | 3602 a 3605 | 0 | - |
| `GEN_FOOD_FOXES`=6 | 3 | 2427 a 2660 | 262 a 324 | 0,06 a 0,21 |
| `GEN_FOOD_FOXES`=20 | 3 | 1151 a 1290 | 612 a 644 | 0,028 a 0,056 |
| Rocas 0 % | 3 | 3660 a 3678 | 10 a 15 | 0,46 a 0,81 |
| Rocas 15 % | 3 | 1474 a 1487 | 501 a 503 | 0,016 a 0,019 |
| Rocas 30 % | 3 | 1535 a 1551 | 359 a 369 | 0,025 |

(Rocas 5 % es la base.) "Amplitud relativa lenta" es desviación estándar / media de la serie sin periodos cortos.

Extinciones (generación en que la especie llega a 0), por semilla 1 / 2 / 3:

- `GEN_PROC_RABBITS`=8: zorros 9171 / 2915 / 1974.
- `GEN_PROC_FOXES`=5: conejos 79 / 493 / 71. Los zorros no se extinguen en ninguna (quedan unos 130 a 150); con
  `GEN_PROC_FOXES`=5 y `GEN_FOOD_FOXES`=10 en una prueba aparte sin conejos (150 zorros, 3000 generaciones, semilla 1)
  los zorros bajaron a 72 pero no se extinguieron, mientras que con `GEN_PROC_FOXES` de 9, 10 o 20 (hambre 6 o 10) se
  extinguieron antes de la generación 10. La causa no se probó.
- `GEN_FOOD_FOXES`=3: zorros 112 / 101 / 123 (los conejos quedan en unos 3600 y no se extinguen).

## Efecto de las rocas

- Con 0 % de rocas, los conejos suben a unos 3670 y los zorros caen de 150 a unos 10 a 15, con grandes altibajos
  irregulares (amplitud relativa 0,46 a 0,81, rango 3 a 34 zorros entre percentiles 5 y 95, semilla 1). No se extinguen
  en 10 000 generaciones, pero quedan cerca de cero.
- Con 5 %, 15 % y 30 % los zorros se mantienen en 489, 502 y 365 (media de las 3 semillas) y la variación lenta es la más baja con 15 % (0,016 a 0,019 en zorros, 0,022 a 0,025 en conejos).
- Resumen: sin rocas la población de zorros es la menos estable; la variación lenta mínima aparece con 15 %.
  Que sea un efecto de las rocas como refugio de conejos es una hipótesis no probada (no se midió la distribución
  espacial).

## Efecto de cada parámetro

- **`GEN_PROC_RABBITS`**: crece de 2 a 5 y los zorros caen de unos 680 a 27 a 52 (con mayor variación relativa); con 8 los
  zorros se extinguen en 2000 a 9000 generaciones. Reproducción más lenta de los conejos desfavorece a los zorros.
- **`GEN_PROC_FOXES`**: con 5 se extinguen los conejos; con 10 la coexistencia tiene los zorros más numerosos (unos 654) y
  los conejos más bajos (unos 940); con 40 los zorros bajan a 84 a 110 y la variación relativa sube a 0,31 a 0,45.
- **`GEN_FOOD_FOXES`**: con 3 los zorros se extinguen en unas 100 a 123 generaciones; con 6, 10 y 20 coexisten y los zorros
  suben de 262 a 324, a 489, a 612 a 644 mientras los conejos bajan de 2427 a 2660, a 1761, a 1151 a 1290.
- **Ventana de coexistencia en los barridos**: coexisten las 3 semillas en 10 de las 13 configuraciones; las 3
  configuraciones que no (`GEN_PROC_RABBITS`=8, `GEN_PROC_FOXES`=5, `GEN_FOOD_FOXES`=3) fallan igual en las 3 semillas.

## Ciclo débil (única señal)

Con `GEN_PROC_FOXES`=10 el análisis a 10 000 generaciones da un ciclo lento de periodo 80 (autocorrelación 0,38) solo en
los zorros de la semilla 2. A 20 000 generaciones los zorros superan 0,3 en las 3 semillas (periodos 80, 81 y 82;
autocorrelación 0,39, 0,37, 0,35) y los conejos solo en la semilla 1 (periodo 82; 0,30, con zorros 26 generaciones
después). La amplitud es pequeña (desviación/media 0,04 a 0,07) y los valores están pegados al umbral, así que se
describe como **oscilación débil de periodo ~80, no como ciclo establecido**. La ventana de suavizado ahí es 44. No se probó
si es un efecto del suavizado ni su mecanismo.

## Sensibilidad al umbral

Número de corridas de los barridos (39) con ciclo lento en alguna especie: 0 con umbral 0,5; 1 con 0,3; 9 con 0,2;
19 con 0,1. Con 0,1 y 0,2 los periodos detectados son muy dispares (de ~80 a ~2600 generaciones, con desfases de signo
cambiante), lo que sugiere ruido y no un ciclo. La conclusión "sin ciclos" no depende de elegir 0,3 frente a 0,5; sí
cambiaría con umbrales mucho más permisivos.

## Qué no se probó

- No se probaron otros tamaños de mundo, otras densidades iniciales, ni corridas con más de 20 000 generaciones.
- Los ciclos con periodo menor que la ventana de suavizado (84 en la base) no son detectables con este método.
- Las causas de la oscilación rápida, de la desaparición de ciclos y del efecto de las rocas no se verificaron.

## Archivos

- `experiments/ecosystem_runs.py`: `analyze`, barridos y gráficas. `tests/test_ecosystem.py`: pruebas.
- `experiments/results/ecosystem_summary.csv` y `experiments/results/ecosystem/*.csv`.
- Figuras en `docs/report/figuras/`: `eco_base_serie.png` (base: corrida completa y 100 generaciones),
  `eco_series_rocas.png`, `eco_series_parametros.png`, `eco_estabilidad.png` (resumen de estabilidad).
