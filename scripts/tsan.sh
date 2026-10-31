#!/usr/bin/env bash
# ThreadSanitizer run of the Pthreads and OpenMP engines. Meant to run in a Linux container with
# the repo mounted at /src:
#   docker run --rm --security-opt seccomp=unconfined -e TSAN_IMAGE=gcc:14 -v "<repo>:/src" -w /src gcc:14 bash scripts/tsan.sh
# seccomp=unconfined lets setarch disable ASLR: with vm.mmap_rnd_bits=32 (the WSL2 kernel) TSan
# dies with "unexpected memory mapping" otherwise. The script re-executes itself under
# "setarch <arch> -R" for that reason.
# Builds without -static (incompatible with TSan) into /tmp, runs 20x20 and unbal01 at 4 and 8
# threads, and writes the evidence to experiments/results/tsan_pth.txt and tsan_omp.txt.
# Variants (environment): CXX=clang++ with OMP_TOOL_LIBRARIES=libarcher.so, SKIP_PTH=1 and
# OMP_RESULT=<file> run only OpenMP under LLVM's Archer, which instruments the OpenMP barriers.
# COVERAGE=1 (clang only) also builds with source coverage and appends the call counts of
# rebalance, adaptiveBands and fillRowCosts, to prove that the adaptive rebalancing was executed.
# Sections: Pthreads and clang/Archer OpenMP must have 0 reports. OpenMP built with gcc runs on the
# uninstrumented libgomp, where reports are EXPECTED false positives (see the note it writes); that
# section only fails if a run crashes or its output differs from the sequential one.
# Exit code: 0 if every section met its expectation, 1 otherwise.
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
[ -n "${COVERAGE:-}" ] && CXXFLAGS="$CXXFLAGS -fprofile-instr-generate -fcoverage-mapping"
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

report() { # name file-to-write binary expect-warnings(0|1)
  local name=$1 file=$2 bin=$3 expect=${4:-0}
  local sec=0 total=0
  rm -f $B/prof_*.profraw
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
    echo "schedule: default (adaptive for OpenMP, REBALANCE_EVERY=50 in engine/simulator.hpp)"
    if [ "$expect" = 1 ]; then
      echo
      echo "EXPECTED RESULT OF THIS SECTION: TSan warnings. libgomp (GCC OpenMP runtime) is not"
      echo "instrumented, so TSan cannot see the happens-before edges of 'omp barrier' and of the"
      echo "implicit barrier of 'omp single'. These warnings are false positives caused by that, not"
      echo "engine races. The same runs with Archer, which models the OpenMP barriers, are in the"
      echo "Archer evidence file and must have 0 warnings. This section fails only if a run crashes"
      echo "or its output differs from the sequential output."
    fi
    echo
  } > "$file"
  for inp in 20x20 unbal01; do
    for t in 4 8; do
      local log=$B/run_${name}_${inp}_$t.log
      LLVM_PROFILE_FILE=$B/prof_%p.profraw $bin --threads $t --dump-all < $B/in_$inp > $B/out.txt 2> $log
      local rc=$?
      local warns
      warns=$(grep -c 'WARNING: ThreadSanitizer' $log)
      total=$((total + warns))
      local same=no
      cmp -s $B/out.txt $B/expected_$inp && same=yes
      {
        echo "--- $(basename $bin) --threads $t < input $inp"
        echo "exit code: $rc; TSan warnings: $warns; output identical to sequential: $same"
        echo "distinct SUMMARY lines (count of each, complete list):"
        grep 'SUMMARY: ThreadSanitizer' $log | sed 's/ (BuildId.*) in / in /' | sort | uniq -c | sort -rn | sed 's/^/  /'
        echo "first 120 lines of the log:"
        grep -v '^eco_\|^threads=' $log | head -120
        grep '^threads=\|^imbalance\|time' $log | head -3
        echo
      } >> "$file"
      if [ "$same" != yes ]; then sec=1; fi
      if [ "$expect" = 1 ]; then
        if [ "$rc" -ne 0 ] && [ "$rc" -ne 66 ]; then sec=1; fi
      else
        if [ "$rc" -ne 0 ] || [ "$warns" -ne 0 ]; then sec=1; fi
      fi
    done
  done
  {
    echo "=== distinct SUMMARY lines over all 4 runs of this section (count, complete) ==="
    cat $B/run_${name}_*.log | grep 'SUMMARY: ThreadSanitizer' | sed 's/ (BuildId.*) in / in /' | sort | uniq -c | sort -rn | sed 's/^/  /'
    echo "(none)" | grep -q . && [ "$total" -eq 0 ] && echo "  (none)"
    echo
  } >> "$file"
  if [ -n "${COVERAGE:-}" ]; then
    echo "profile files merged: $(ls $B/prof_*.profraw | wc -l)" > $B/nprof.txt
    llvm-profdata merge -o $B/all.profdata $B/prof_*.profraw
    {
      echo "=== source coverage of the same 4 runs (llvm-cov, FNDA = executions of the function) ==="
      cat $B/nprof.txt
      echo "Rounds of rebalancing: 20x20 has 1000 gens -> 20, unbal01 has $GENS_UNBAL gens -> $((GENS_UNBAL / 50)); two thread counts each."
      echo "Expected adaptiveBands calls (thread 0, once per round): $(( 2 * (20 + GENS_UNBAL / 50) )). Expected rebalance calls (every thread): $(( (20 + GENS_UNBAL / 50) * 12 ))."
      echo "Counters are not atomic, so measured counts of the per-thread functions can be lower."
      llvm-cov export $bin -instr-profile=$B/all.profdata -format=lcov | grep '^FNDA' | grep -i 'rebalance\|adaptiveBands\|fillRowCosts\|fillRowOwners' | sed 's/^/  /'
      echo
    } >> "$file"
  fi
  {
    if [ "$expect" = 1 ]; then
      echo "overall: $total TSan warnings in 4 runs, EXPECTED for this section (uninstrumented libgomp, see the note at the top); outputs identical to sequential in all runs: $([ $sec -eq 0 ] && echo yes || echo NO, see above)"
    else
      echo "overall: $total TSan warnings in 4 runs, expected 0; outputs identical to sequential in all runs: $([ $sec -eq 0 ] && echo yes || echo NO); section $([ $sec -eq 0 ] && echo PASS || echo FAIL)"
    fi
  } >> "$file"
  [ $sec -ne 0 ] && status=1
}

# Negative control for Archer: the same tiny program with and without its barrier.
control() { # file
  local f=$1 d v
  cat > $B/ctl.cpp <<'EOF'
#include <omp.h>
#include <cstdio>
int a[16];
int main() {
#pragma omp parallel num_threads(4)
  {
    a[omp_get_thread_num()] = 1;
#ifdef BAR
#pragma omp barrier
#endif
    int s = 0;
    for (int i = 0; i < 4; i++) s += a[i];
    if (s != 4) puts("x");
  }
}
EOF
  echo "=== negative control (4-thread program: each thread writes a[id], optional barrier, reads a[0..3]) ===" >> "$f"
  for v in with_barrier no_barrier; do
    d=""; [ $v = with_barrier ] && d=-DBAR
    $CXX $d -fopenmp -fsanitize=thread -g $B/ctl.cpp -o $B/ctl || return
    $B/ctl > /dev/null 2> $B/ctl.err
    echo "  $v: exit code $?, TSan warnings $(grep -c 'WARNING: ThreadSanitizer' $B/ctl.err)" >> "$f"
  done
  echo "  expected: with_barrier 0 warnings; no_barrier at least 1 (so Archer still detects a missing barrier)" >> "$f"
}

expect_fp=0
case "$CXX" in *clang*) ;; *) expect_fp=1 ;; esac
[ -z "${SKIP_PTH:-}" ] && report pthreads $OUT/tsan_pth.txt $B/eco_pth 0
report openmp $OMP_RESULT $B/eco_omp $expect_fp
[ "$expect_fp" = 0 ] && [ -n "${OMP_TOOL_LIBRARIES:-}" ] && control $OMP_RESULT
echo "tsan.sh status=$status"
exit $status
