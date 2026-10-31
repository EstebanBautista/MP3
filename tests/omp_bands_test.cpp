// Native test of the cuts OmpSimulator really uses, run by tests/test_conformance.py on a world whose
// path is the first argument. Everything is exact: bands depend only on the world and the thread
// count, never on timing. Exit code 0 means all passed.
#include <cstdio>

#include "bands.hpp"
#include "io.hpp"
#include "simulator.hpp"

static const int THREADS = 8;
static int failures = 0;

#define CHECK(cond)                                                   \
    do {                                                              \
        if (!(cond)) {                                                \
            printf("%s:%d: failed: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                               \
        }                                                             \
    } while (0)

static void load(const char* path, World& w, int generations) {
    FILE* f = fopen(path, "rb");
    char err[160];
    if (!f || !readWorld(f, w, err, sizeof err)) {
        printf("cannot read %s\n", path);
        exit(1);
    }
    fclose(f);
    w.cfg.nGen = generations;
}

static bool sameBands(const Band* a, const Band* b) {
    for (int t = 0; t < THREADS; t++)
        if (a[t].first != b[t].first || a[t].last != b[t].last) return false;
    return true;
}

// The bands of an OmpSimulator run of the given length.
static void runOmp(const char* path, int generations, const char* schedule, Band* out) {
    World w;
    load(path, w, generations);
    OmpSimulator sim;
    CHECK(sim.setExtraOption(schedule));
    sim.run(w, THREADS, nullptr);
    CHECK(sim.threadsUsed(THREADS) == THREADS);
    for (int t = 0; t < THREADS; t++) {
        out[t] = sim.finalBands()[t];
        // Moves are routed by owner, so a stale one would make two threads write the same cell, with
        // the same final cells and no trace in the output.
        for (int x = out[t].first; x < out[t].last; x++) CHECK(sim.finalRowOwners()[x] == t);
    }
}

// The bands that the cost of the world after the given generations should produce.
static void expectedCuts(const char* path, int generations, int* cost, Band* out) {
    World w;
    load(path, w, generations);
    SeqSimulator().run(w, 1, nullptr);
    fillRowCosts(w, w.cur, Band{0, w.cfg.rows}, OmpSimulator::ANIMAL_WEIGHT, cost);
    adaptiveBands(cost, w.cfg.rows, THREADS, out);
}

static long long largestBand(const int* cost, const Band* bands) {
    long long largest = 0;
    for (int t = 0; t < THREADS; t++) {
        long long sum = 0;
        for (int x = bands[t].first; x < bands[t].last; x++) sum += cost[x];
        if (sum > largest) largest = sum;
    }
    return largest;
}

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const char* path = argv[1];
    const int every = OmpSimulator::REBALANCE_EVERY;

    World shape;
    load(path, shape, 0);
    const int rows = shape.cfg.rows;
    int* cost = new int[rows];
    Band fixed[THREADS], actual[THREADS], expected[THREADS], first[THREADS];
    staticBands(rows, THREADS, fixed);

    // The first cut uses the initial world, and costs less at its largest than the static bands.
    runOmp(path, 1, "adaptive", first);
    expectedCuts(path, 0, cost, expected);
    CHECK(sameBands(first, expected));
    CHECK(!sameBands(first, fixed));
    CHECK(largestBand(cost, first) < largestBand(cost, fixed));

    // No new cut before REBALANCE_EVERY generations.
    runOmp(path, every, "adaptive", actual);
    CHECK(sameBands(actual, first));

    // Later cuts use the world of that moment, and the population does move them.
    bool moved = false;
    for (int k = 1; k <= 5; k++) {
        runOmp(path, k * every + 1, "adaptive", actual);
        expectedCuts(path, k * every, cost, expected);
        CHECK(sameBands(actual, expected));
        moved = moved || !sameBands(actual, first);
    }
    CHECK(moved);

    // The control keeps the static bands for the whole run.
    runOmp(path, 5 * every + 1, "static", actual);
    CHECK(sameBands(actual, fixed));

    delete[] cost;
    if (failures) printf("%d failures\n", failures);
    return failures ? 1 : 0;
}
