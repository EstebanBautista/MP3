#!/bin/sh
# Supplementary Linux measurement inside the gcc:14 container (WSL2 + Docker Desktop, not native).
# Run from the host:  docker run --rm -v "<repo>:/work" -w /work gcc:14 sh scripts/perf_linux.sh
set -e
REPS=7
CASES="200x200 large1000x1000"
apt-get update -qq && apt-get install -y -qq cmake >/dev/null
cmake -S . -B build-linux -DCMAKE_BUILD_TYPE=Release -DECO_STATIC=OFF >/dev/null
cmake --build build-linux -j4 -- VERBOSE=1 2>&1 | grep -E "eco_omp|sim_omp.cpp" | head -4 | cut -c1-300 > experiments/data/linux_build_cmds.txt || true
python3 experiments/measure.py env --build build-linux --reps $REPS --cases $CASES \
  --out experiments/results/environment_linux.txt
g++ -O3 -std=gnu++17 -fopenmp -pthread experiments/barrier_bench.cpp -o build-linux/barrier_bench
build-linux/barrier_bench 40000 $REPS > experiments/results/barriers_linux.csv
python3 -u experiments/measure.py run --build build-linux --reps $REPS \
  --cases $CASES --csv experiments/results/performance_linux.csv
