#!/usr/bin/env bash
# ThreadSanitizer run of the Pthreads and OpenMP engines. Meant to run in a Linux container with
# the repo mounted at /src:
#   docker run --rm --security-opt seccomp=unconfined -e TSAN_IMAGE=gcc:14 #     -v "<repo>:/src" -w /src gcc:14 bash scripts/tsan.sh
# seccomp=unconfined lets setarch disable ASLR: with vm.mmap_rnd_bits=32 (the WSL2 kernel) TSan
# dies with "unexpected memory mapping" otherwise. The script re-executes itself under
# "setarch <arch> -R" for that reason.
# Builds without -static (incompatible with TSan) into /tmp, runs 20x20 and unbal01 at 4 and 8
# threads, and writes the evidence to experiments/results/tsan_pth.txt and tsan_omp.txt.
# Variants (environment): CXX=clang++ with OMP_TOOL_LIBRARIES=libarcher.so, SKIP_PTH=1 and
# OMP_RESULT=<file> run only OpenMP under LLVM's Archer, which instruments the OpenMP barriers.
# Exit code: 0 if every run finished with the sequential output and no TSan report, 1 otherwise.
set -u
if [ -z "${TSAN_NOASLR:-}" ]; then
  export TSAN_NOASLR=1
  exec setarch "$(uname -m)" -R bash "$0" "$@"
fi
cd "$(dirname "$0")/.."
OUT=experiments/results
B=/tmp/tsan_build
CXX=${CXX:-g++}
OMP_RESULT=${OMP_RESULT:-$OUT/tsan_omp.txt}
GENS_UNBAL=${GENS_UNBAL:-200}
mkdir -p "$OUT" "$B"
CXXFLAGS="-std=c++17 -fsanitize=thread -g -O1 -Wall -Wextra -Iengine"
CORE="engine/world.cpp engine/io.cpp engine/cli.cpp"
status=0

$CXX $CXXFLAGS $CORE engine/main_seq.cpp engine/sim_seq.cpp -o $B/eco_seq || exit 1
$CXX $CXXFLAGS -pthread $CORE engine/main_pth.cpp engine/sim_pth.cpp -o $B/eco_pth || exit 1
$CXX $CXXFLAGS -fopenmp $CORE engine/main_omp.cpp engine/sim_omp.cpp -o $B/eco_omp || exit 1

# Inputs: the 20x20 example as is, unbal01 with fewer generations (field 4 of the header).
cp ecosystem_examples/input20x20 $B/in_20x20
awk 'NR==1{$4='"$GENS_UNBAL"'} {print}' ecosystem_examples/input100x100_unbal01 > $B/in_unbal01
tr -d '\r' < $B/in_20x20 > $B/in_20x20.lf && mv $B/in_20x20.lf $B/in_20x20
tr -d '\r' < $B/in_unbal01 > $B/in_unbal01.lf && mv $B/in_unbal01.lf $B/in_unbal01

export TSAN_OPTIONS="halt_on_error=0 exitcode=66 second_deadlock_stack=1${TSAN_EXTRA:+ $TSAN_EXTRA}"

for inp in 20x20 unbal01; do
  $B/eco_seq --dump-all < $B/in_$inp > $B/expected_$inp 2> $B/seq_$inp.err
done

report() { # name file-to-write binary
  local name=$1 file=$2 bin=$3
  {
    echo "ThreadSanitizer evidence: $name"
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "image: ${TSAN_IMAGE:-unknown}"
    echo "compiler: $($CXX --version | head -1)"
    echo "OMP_TOOL_LIBRARIES=${OMP_TOOL_LIBRARIES:-}"
    echo "kernel: $(uname -sr), vm.mmap_rnd_bits=$(cat /proc/sys/vm/mmap_rnd_bits 2>/dev/null)"
    echo "cpus: $(nproc)"
    echo "build: $CXX $CXXFLAGS ($name), not static"
    echo "TSAN_OPTIONS=$TSAN_OPTIONS"
    echo "unbal01 generations: $GENS_UNBAL (original input has 10000)"
    echo
  } > "$file"
  for inp in 20x20 unbal01; do
    for t in 4 8; do
      local log=$B/run_${name}_${inp}_$t.log
      $bin --threads $t --dump-all < $B/in_$inp > $B/out.txt 2> $log
      local rc=$?
      local warns
      warns=$(grep -c 'WARNING: ThreadSanitizer' $log)
      local same=no
      cmp -s $B/out.txt $B/expected_$inp && same=yes
      {
        echo "--- $(basename $bin) --threads $t < input $inp"
        echo "exit code: $rc; TSan warnings: $warns; output identical to sequential: $same"
        grep -v '^eco_\|^threads=' $log | head -300
        grep '^threads=\|^imbalance\|time' $log | head -3
        echo
      } >> "$file"
      if [ "$rc" -ne 0 ] || [ "$warns" -ne 0 ] || [ "$same" != yes ]; then status=1; fi
    done
  done
  echo "overall: $([ $status -eq 0 ] && echo 'no reports and identical outputs so far' || echo 'FAILURES, see above')" >> "$file"
}

[ -z "${SKIP_PTH:-}" ] && report pthreads $OUT/tsan_pth.txt $B/eco_pth
report openmp $OMP_RESULT $B/eco_omp
echo "tsan.sh status=$status"
exit $status
