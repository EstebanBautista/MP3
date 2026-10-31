# Hallazgos de los experimentos del ecosistema

Datos para quien redacte el informe. Todo sale de los CSV de `experiments/results/` y se reproduce con
`python experiments/ecosystem_runs.py` (subcomandos `run`, `explore`, `foxonly`, `inject`, `sensitivity`, `plot`).
Cuando algo es una hipótesis no probada, se dice así.

## Resultado en una frase

Las poblaciones **sí suben y bajan de forma periódica**, pero con el periodo corto de reproducción de cada especie
(`GEN_PROC + 1`; unas 4 y 21 generaciones en la base), no con el ciclo lento depredador-presa que la tarea esperaba. No se
demostró que esa oscilación rápida sea una interacción depredador-presa. **No se vio ningún ciclo lento fuerte** en 39
corridas de barrido. Sí aparece una **oscilación lenta débil** (periodo 74-79 generaciones, 5 a 9 % de la media) con
`GEN_PROC_FOXES`=10, y señales aún más débiles, por debajo del umbral, en otras configuraciones. Este resultado vale "a
la sensibilidad del análisis" (ver "Qué detecta el análisis"), no es una prueba de que no exista nada más lento.

## Método

- Mundo 100x100, motor `build/eco_seq.exe` con `--stats-file`, 10 000 generaciones, semillas 1, 2 y 3 (controlan la
  posición inicial de animales y rocas).
- **Configuración base**, elegida una sola vez, antes de los barridos, con la exploración de
  `experiments/results/ecosystem_explore.csv` (10 combinaciones: conejos 700 a 3000, zorros 70 a 300, 500 rocas, parámetros
  3/20/10 y 3/9/6, 3000 generaciones, semilla 1; en las 10 coexistieron las dos especies) y no cambiada después:
  1500 conejos (15 %), 150 zorros (1,5 %), 500 rocas (5 %), `GEN_PROC_RABBITS`=3, `GEN_PROC_FOXES`=20,
  `GEN_FOOD_FOXES`=10 (los valores de los ejemplos de la tarea).
- Barridos, un parámetro a la vez desde la base (13 configuraciones x 3 semillas = 39 corridas):
  `GEN_PROC_RABBITS` en {2, 3, 5, 8}; `GEN_PROC_FOXES` en {5, 10, 20, 40}; `GEN_FOOD_FOXES` en {3, 6, 10, 20}; rocas 0, 5, 15,
  30 % (0, 500, 1500, 3000). Los valores se fijaron antes de correr.
- Seis corridas largas (20 000 generaciones, mismas semillas) de la base y de `GEN_PROC_FOXES`=10, agregadas después de ver
  una señal débil a 10 000 en esta última. Están marcadas `long` en el resumen.
- Los CSV crudos pesan unos 125 KB (10 000 generaciones) o 250 KB (20 000): ninguno se acerca a 500 KB, no se comprimieron
  ni se diezmaron.

### Análisis (`analyze`)

1. Se descarta el primer 20 % de la serie (transitorio) y la tendencia lineal.
2. **Periodo crudo**: primer pico de autocorrelación >= 0,3 de la serie cruda. Es la oscilación rápida.
3. **Patrón rápido**: los periodos crudos <= 50 se quitan restando a cada generación el valor medio de su fase módulo el
   mínimo común múltiplo de esos periodos (`fold`: 84 en la base, 44 con `GEN_PROC_FOXES`=10, 42 con `GEN_PROC_RABBITS`=5,
   164 con `GEN_PROC_FOXES`=40). Esto elimina el patrón exacto sin promediar períodos vecinos (una media móvil de 84 anula el
   periodo 84 y atenúa los cercanos; la primera versión del análisis la usaba y subestimó la señal débil).
4. **Periodo lento**: primer pico de autocorrelación >= **0,3** de la serie restante (suavizada 9 generaciones), con
   autocorrelación negativa antes del pico, entre 20 generaciones y un tercio de la serie. Si no hay, `None`.
5. **Grado**: `strong` si además el pico llega a 0,6 y la amplitud (desviación de la serie filtrada alrededor del periodo
   / media) a 10 %; `weak` si solo supera 0,3; `none` si no hay pico.
6. **Desfase** `fox_lag`: máximo de la correlación cruzada de las dos series filtradas alrededor del periodo
   (positivo = los zorros van detrás de los conejos).
7. Variación `cv`: desviación/media de la segunda mitad de la serie sin el patrón, sin tendencia lineal (para que la deriva
   inicial no cuente). `slowcv` es lo mismo tras una media móvil de `fold` generaciones (variación más lenta que el
   patrón rápido).

Pruebas con señales sintéticas (`tests/test_ecosystem.py`): senoides de periodo 100 con desfase 25; senoide lenta (1000) más
rápida (10); patrones exactos de periodo 4 y 21 más un ciclo débil de periodo 90 (6 %), recuperado con desfase 22; ruido
blanco y ruido rojo (AR(1)) no dan ciclo.

### Qué detecta el análisis (`ecosystem_injection.csv`)

Se multiplicó por (1 + a sen(2 pi g / P)) las series reales de 4 configuraciones (base, hambre 6, conejos 5, sin rocas) x 3
semillas (12 casos por celda; zorros desfasados P/4) y se contó si algún periodo hallado queda a menos del 15 % de P:

| Periodo inyectado | 2 % | 5 % | 10 % | 20 % |
|---|---|---|---|---|
| 40 | 6/12 | 9/12 | 11/12 | 12/12 |
| 60 | 6/12 | 9/12 | 11/12 | 12/12 |
| 84 | 3/12 | 3/12 | 3/12 | 8/12 |
| 100, 150, 300 | 6/12 | 10/12 | 11/12 | 12/12 |
| 600, 1000 | 6/12 | 10/12 | 12/12 | 12/12 |
| 2000 | 5/12 | 10/12 | 11/12 | 12/12 |

- Con amplitud >= 10 % de la media se detectan casi todos (11 o 12 de 12) entre 40 y 2000 generaciones. A 5 % se detectan
  9 o 10 de 12; a 2 %, la mitad. Un ciclo de 5 % o menos puede pasar inadvertido.
- Los fallos a 10 % salvo el periodo 84 son 6 casos, todos de la semilla 1 de hambre 6 (serie de zorros más ruidosa).
- **Punto ciego**: un ciclo cuyo periodo coincide con `fold` (84 en tres de las cuatro configuraciones) se resta junto con el
  patrón. Solo se detectó donde `fold` era 42 (conejos 5). No se probaron periodos menores que 40.
- El desfase inyectado se recuperó (dentro de 15 % o 3 generaciones) en 153 de 197 detecciones con amplitud >= 10 %.
- Falsos positivos: en 150 series de ruido rojo (AR(1), phi 0,99) se halló un ciclo falso en 6 con 6000 generaciones y en 0
  con 10 000 (`sensitivity`).

## Resultados de los barridos

### Oscilación rápida

Periodos de la serie cruda, iguales en las 3 semillas: conejos `GEN_PROC_RABBITS`+1 (3, 4 o 6) y zorros `GEN_PROC_FOXES`+1
(11, 21 o 41). En la base (semilla 1, tras el transitorio), el coeficiente de variación de la serie cruda es 0,23 (conejos) y
0,21 (zorros): en 100 generaciones los conejos van de unos 1250 a 2700 y los zorros hacen dientes de sierra de 21
generaciones entre 300 y 680 (`eco_base_serie.png`). La coincidencia con `GEN_PROC + 1` es lo observado; el mecanismo (los
periodos fijos de reproducción y la regla `(G+X+Y) mod P`) no se verificó.

### Transitorio inicial (`eco_transitorio.png`; semilla 1, media móvil de 21 generaciones)

- **Base**: los conejos suben de 1500 a un máximo crudo de 4262 en la generación 20 y los zorros bajan a 126 en esa generación; los
  zorros suben después a unos 500 hacia la generación 110 mientras los conejos bajan a unos 1770; hay un rebote pequeño
  (conejos 1666 en la gen. 210, 1766 en la 310) y luego se estabilizan (1674 en la 510, 1720 en la 1010). Es un solo sobreimpulso
  amortiguado, no un ciclo que se repita.
- **`GEN_FOOD_FOXES`=20**: mismo máximo (4254 en la gen. 20) y un solo sobreimpulso pequeño que se apaga en unas 150
  generaciones (conejos 1313 en la gen. 110, 1148 en la 150, luego 1150 a 1200; zorros alrededor de 650).
- **Sin rocas**: igual arranque, pero los zorros suben a unos 480 suavizados (660 crudos) hacia la generación 105 y luego **declinan
  durante miles de generaciones**: 349 en la gen. 310, 109 en la 1010, 48 en la 2010, 21 en la 3010 y 2 a 20 de la 4010 en adelante.

### Derivas largas (la población no queda en un nivel fijo)

- `GEN_PROC_RABBITS`=5 (semilla 1): los zorros pasan de unos 300 en la generación 150 a unos 22 en la 1510 (172 en la 510, 43 en la 1010) y se
  quedan en 18 a 30 el resto de la corrida; los conejos suben de 1630 a 2700.
- `GEN_FOOD_FOXES`=6 (semilla 1): zorros 330 a 357 hasta la generación 2000, luego 298 (gen. 3010), 255 (4010), 165 (5010) y 243 (8010);
  los conejos suben de 2400 a 3075 en la 5010. Cambio de nivel en las generaciones 3000 a 5000.
- `GEN_PROC_FOXES`=40 (semilla 1): zorros 315 (gen. 210), 83 (2010), 25 (4010) y 91 a 98 de la 5010 en adelante.

Por eso "estable" no significa "constante": la amplitud lenta incluye derivas de este tipo en varias configuraciones.

### Resultados por parámetro (media tras el transitorio, rango de las 3 semillas)

| Configuración | Coexisten (de 3) | Conejos | Zorros | Variación lenta `slowcv` conejos / zorros |
|---|---|---|---|---|
| Base (5 % rocas, 3/20/10) | 3 | 1684 a 1830 | 472 a 508 | 0,033 a 0,057 / 0,026 a 0,058 |
| `GEN_PROC_RABBITS`=2 | 3 | 1828 a 1836 | 677 a 682 | 0,035 a 0,039 / 0,023 a 0,024 |
| `GEN_PROC_RABBITS`=5 | 3 | 2572 a 2655 | 27 a 52 | 0,007 a 0,011 / 0,14 a 0,20 |
| `GEN_PROC_RABBITS`=8 | 0 | 1795 a 1870 | 0 a 4 | - |
| `GEN_PROC_FOXES`=5 | 0 | 0 | 126 a 152 | - |
| `GEN_PROC_FOXES`=10 | 3 | 935 a 950 | 653 a 655 | 0,058 a 0,070 / 0,031 a 0,040 |
| `GEN_PROC_FOXES`=40 | 3 | 3319 a 3489 | 84 a 110 | 0,018 a 0,025 / 0,08 a 0,16 |
| `GEN_FOOD_FOXES`=3 | 0 | 3602 a 3605 | 0 | - |
| `GEN_FOOD_FOXES`=6 | 3 | 2427 a 2660 | 262 a 324 | 0,027 a 0,036 / 0,055 a 0,089 |
| `GEN_FOOD_FOXES`=20 | 3 | 1151 a 1290 | 612 a 644 | 0,049 a 0,077 / 0,023 a 0,035 |
| Rocas 0 % | 3 | 3660 a 3678 | 10 a 15 | 0,004 a 0,005 / 0,44 a 0,53 |
| Rocas 15 % | 3 | 1474 a 1487 | 501 a 503 | 0,019 a 0,025 / 0,014 a 0,019 |
| Rocas 30 % | 3 | 1535 a 1551 | 359 a 369 | 0,023 a 0,026 / 0,024 a 0,026 |

(Rocas 5 % es la base.) Los valores de `GEN_PROC_RABBITS`=5, `GEN_PROC_FOXES`=40 y rocas 0 % incluyen derivas de varios
miles de generaciones (ver arriba), aunque `slowcv` se mide solo en la segunda mitad y sin tendencia lineal.

Extinciones (generación en que la especie llega a 0), semillas 1 / 2 / 3:

- `GEN_PROC_RABBITS`=8: zorros 9171 / 2915 / 1974.
- `GEN_PROC_FOXES`=5: conejos 79 / 493 / 71; los zorros no se extinguen (quedan 126 a 152). Prueba aparte sin conejos
  (`ecosystem_foxonly.csv`, 150 zorros, 3000 generaciones, semilla 1): con `GEN_PROC_FOXES`=5 y `GEN_FOOD_FOXES`=10 los zorros
  fueron 142 (gen. 10), 262 (20), 248 (50), 143 (500) y 72 (2999), sin extinguirse; con `GEN_PROC_FOXES`=10 o 20 y
  `GEN_FOOD_FOXES`=10 se extinguieron en la generación 10, y con 9 y 6 en la 6. La causa de la diferencia no se probó.
- `GEN_FOOD_FOXES`=3: zorros 112 / 101 / 123 (los conejos quedan en unos 3600).
- Las otras 10 configuraciones de 13 conservan las dos especies en las 3 semillas.

### Efecto de las rocas (descriptivo; `eco_series_rocas.png`)

- 0 %: los conejos suben a unos 3670 y los zorros acaban entre 10 y 15 en las 3 semillas, con altibajos irregulares (`slowcv` 0,44 a
  0,53; semilla 1: percentiles 5 y 95 de 3 y 34 zorros). Antes de eso los zorros suben a unos 480 (ver transitorio).
  No se extinguen en 10 000 generaciones pero quedan cerca de 0.
- 5, 15 y 30 %: zorros 489, 502 y 365 de media (3 semillas); `slowcv` de zorros más bajo con 15 % (0,014 a 0,019, frente a 0,026 a 0,058 con 5 %).
- Con rocas la variación residual de los conejos tras quitar el patrón (`rabbit_cv` en el resumen) es mayor que sin ellas: 0,14 a 0,20 con 15 % frente a 0,009 sin rocas.
  No se investigó por qué.
- Que las rocas actúen como refugio de conejos o rompan la sincronía espacial es una hipótesis no probada (no se midió la
  distribución espacial).

### Asociaciones entre parámetro y resultado (no se probó causalidad)

- `GEN_PROC_RABBITS` de 2 a 5: los zorros bajan de unos 680 a 27 a 52; con 8 se extinguen en 2000 a 9000 generaciones.
- `GEN_PROC_FOXES`: con 5 se extinguen los conejos; con 10, zorros más numerosos (unos 654) y conejos más bajos (unos 940); con 40, zorros 84 a 110.
- `GEN_FOOD_FOXES`: con 3 los zorros se extinguen en 100 a 123 generaciones; con 6, 10 y 20 los zorros suben de 262 a 324, a 489, a 612 a 644
  y los conejos bajan de 2427 a 2660, a 1761, a 1151 a 1290.

## Oscilación lenta débil

Con `GEN_PROC_FOXES`=10 (`fold`=44), análisis de las 6 corridas (3 de 10 000 y 3 de 20 000 generaciones):

| Corrida | Periodo conejos | Periodo zorros | Pico de autocorrelación (conejos / zorros) | Amplitud (% de la media) | Desfase `fox_lag` |
|---|---|---|---|---|---|
| 10 000, semilla 1 | - | 74 | - / 0,35 | - / 4,6 | 22 |
| 10 000, semilla 2 | 77 | 76 | 0,37 / 0,44 | 8,9 / 5,8 | 22 |
| 10 000, semilla 3 | - | - | ambas < 0,3 (a 0,2: 79 y 75) | - | 22 (con umbral 0,2) |
| 20 000, semilla 1 | 78 | 77 | 0,40 / 0,45 | 8,5 / 5,5 | 23 |
| 20 000, semilla 2 | 77 | 76 | 0,33 / 0,41 | 8,6 / 5,7 | 22 |
| 20 000, semilla 3 | 79 | 76 | 0,32 / 0,40 | 8,7 / 5,5 | 23 |

- En las 6 corridas aparece un pico de periodo 74 a 79 con correlación cruzada de 0,92 a 0,94 entre conejos y zorros, y los
  **zorros van 22 a 23 generaciones detrás de los conejos**. Con umbral 0,3 se detecta en 5 de las 6; con 0,2, en las 6 (período 74 a 79).
- Es débil: amplitud de 5 a 9 % de la media, picos de autocorrelación de 0,32 a 0,45, y se describe como `weak`, no `strong`.
- **Esto no demuestra una interacción depredador-presa.** Los periodos hallados (74 a 79) están cerca de múltiplos de los
  periodos rápidos 4 y 11 (por ejemplo 76 = 19 x 4, 77 = 7 x 11), así que un batido entre los dos temporizadores de reproducción no
  se descarta. No se probó.
- Con otras configuraciones, por debajo del umbral 0,3 y solo con umbral 0,2 aparecen: rocas 15 % semilla 1 (periodos 88 y 413) y semilla 3
  (76; desfase 25), y hambre 20 semilla 3 (105; desfase 34). Con 0,2 también aparece `GEN_PROC_RABBITS`=5 semilla 3 con periodo 2267 y desfase
  -1114, que por su valor parece ruido. La base de 20 000 generaciones no da picos con 0,2 (con 0,1 da periodos de 472 a 5200,
  dispersos).

## Sensibilidad al umbral (`ecosystem_sensitivity.csv`, 39 corridas de barrido)

Corridas con periodo lento en alguna especie: 0 con umbral 0,5; 2 con 0,3 (`GEN_PROC_FOXES`=10, semillas 1 y 2); 7 con 0,2; 22 con 0,1.
Con 0,1 los periodos van de unos 76 a 2600 generaciones con desfases de signo cambiante, lo que parece ruido. Los tres periodos de
`GEN_PROC_FOXES`=10 se agrupan en 74 a 79 con 0,2; el resto de las detecciones con 0,2 y 0,1 no se repiten entre semillas.

## Qué no se probó

- Otros tamaños de mundo, otras densidades iniciales, corridas de más de 20 000 generaciones.
- Periodos inferiores a 40 generaciones, y el periodo igual al `fold` (ver punto ciego).
- Las causas de la oscilación rápida, de la oscilación débil de `GEN_PROC_FOXES`=10, de las derivas largas y del efecto de las rocas.

## Archivos

- `experiments/ecosystem_runs.py` (análisis, barridos, gráficas), `tests/test_ecosystem.py`.
- Datos: `experiments/results/ecosystem_summary.csv`, `ecosystem/*.csv`, `ecosystem_explore.csv` (+ `ecosystem_explore/`),
  `ecosystem_foxonly.csv` (+ `ecosystem_foxonly/`), `ecosystem_injection.csv`, `ecosystem_sensitivity.csv`.
- Figuras en `docs/report/figuras/`: `eco_base_serie.png`, `eco_transitorio.png`, `eco_series_rocas.png`,
  `eco_series_parametros.png`, `eco_estabilidad.png`.
