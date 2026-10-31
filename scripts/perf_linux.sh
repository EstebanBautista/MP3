#!/bin/sh
# Supplementary Linux measurement inside the gcc:14 container (WSL2 + Docker Desktop, not native).
# Run from the host:  docker run --rm -v "<repo>:/work" -w /work gcc:14 sh scripts/perf_linux.sh
set -e
apt-get update -qq && apt-get install -y -qq cmake >/dev/null
cmake -S . -B build-linux -DCMAKE_BUILD_TYPE=Release -DECO_STATIC=OFF >/dev/null
cmake --build build-linux -j4 >/dev/null
python3 experiments/measure.py env --build build-linux --reps 3 --out experiments/results/environment_linux.txt
python3 -u experiments/measure.py run --build build-linux --reps 3 \
  --cases 200x200 large1000x1000 --csv experiments/results/performance_linux.csv
