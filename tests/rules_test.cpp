// Native tests of rules.hpp, run by tests/test_edge_cases.py. Exit code 0 means all passed.
#include <cstdio>

#include "bands.hpp"
#include "rules.hpp"

static int failures = 0;

#define CHECK(cond)                                              \
    do {                                                         \
        if (!(cond)) {                                           \
            printf("%s:%d: failed: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                          \
        }                                                        \
    } while (0)

static Cell make(uint8_t kind, int procAge, int foodAge) {
    Cell c{};
    c.kind = kind;
    c.procAge = procAge;
    c.foodAge = foodAge;
    return c;
}

static bool same(const Cell& a, const Cell& b) {
    return a.kind == b.kind && a.procAge == b.procAge && a.foodAge == b.foodAge;
}

static void merge(Cell& dst, const Cell& c) {
    if (c.kind == FOX) mergeFox(dst, c);
    else mergeRabbit(dst, c);
}

// Every order of every triple of candidates gives the same cell.
static void testMergeOrderIndependence() {
    Cell all[4 + 3 * 4];
    int n = 0;
    for (int a = 0; a < 4; a++) all[n++] = make(RABBIT, a, 0);
    for (int a = 0; a < 3; a++)
        for (int h = 0; h < 4; h++) all[n++] = make(FOX, a, h);
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            for (int k = 0; k < n; k++) {
                const Cell t[3] = {all[i], all[j], all[k]};
                static const int orders[6][3] = {{0, 1, 2}, {0, 2, 1}, {1, 0, 2},
                                                 {1, 2, 0}, {2, 0, 1}, {2, 1, 0}};
                Cell first{};
                for (int o = 0; o < 6; o++) {
                    Cell d{};
                    for (int s = 0; s < 3; s++) merge(d, t[orders[o][s]]);
                    if (o == 0) first = d;
                    CHECK(same(d, first));
                }
            }
}

static void testMergeWinners() {
    Cell d = make(RABBIT, 1, 0);
    mergeRabbit(d, make(RABBIT, 2, 0));
    CHECK(d.procAge == 2);
    mergeRabbit(d, make(RABBIT, 0, 0));
    CHECK(d.procAge == 2);

    d = make(FOX, 3, 2);
    mergeFox(d, make(FOX, 3, 1));
    CHECK(d.foodAge == 1);
    mergeFox(d, make(FOX, 3, 5));
    CHECK(d.foodAge == 1);
    mergeFox(d, make(FOX, 4, 9));
    CHECK(d.procAge == 4 && d.foodAge == 9);

    d = make(RABBIT, 9, 0);
    mergeFox(d, make(FOX, 0, 0));
    CHECK(d.kind == FOX);
    mergeRabbit(d, make(RABBIT, 9, 0));
    CHECK(d.kind == FOX && d.procAge == 0);
}

static void testChooseCell() {
    CHECK(chooseCell(0, 0, 2, 3) == 2);
    CHECK(chooseCell(7, 1, 1, 4) == 1);
}

static void initWorld(World& w, int genProc, int genFood, int rows, int cols) {
    Config c{};
    c.genProcRabbits = genProc;
    c.genProcFoxes = genProc;
    c.genFoodFoxes = genFood;
    c.nGen = 1;
    c.rows = rows;
    c.cols = cols;
    w.init(c);
}

// Decided by allgen: the age compared is the one after the move, so a procreating rabbit loses.
static void testProcreatingRabbitLosesConflict() {
    World w;
    initWorld(w, 3, 3, 1, 3);
    w.at(w.cur, 0, 0) = make(RABBIT, 3, 0);
    w.at(w.cur, 0, 2) = make(RABBIT, 2, 0);
    const Move a = decideRabbit(w, w.cur, 0, 0, 0);
    const Move b = decideRabbit(w, w.cur, 0, 0, 2);
    CHECK(a.destY == 1 && a.hasChild && a.animal.procAge == 0);
    CHECK(b.destY == 1 && !b.hasChild && b.animal.procAge == 3);
    applyRabbitMove(w, w.next, a, 0, 0);
    applyRabbitMove(w, w.next, b, 0, 2);
    CHECK(same(w.at(w.next, 0, 1), make(RABBIT, 3, 0)));
    CHECK(same(w.at(w.next, 0, 0), make(RABBIT, 0, 0)));
    CHECK(w.at(w.next, 0, 2).kind == EMPTY);
}

// Decided by allgen: an animal that cannot move ages past the limit, then procreates when it can.
static void testAgeHasNoCap() {
    World w;
    initWorld(w, 3, 3, 1, 2);
    w.at(w.cur, 0, 0) = make(RABBIT, 5, 0);
    w.at(w.cur, 0, 1) = make(ROCK, 0, 0);
    Move m = decideRabbit(w, w.cur, 0, 0, 0);
    CHECK(m.destX == 0 && m.destY == 0 && !m.hasChild && m.animal.procAge == 6);
    w.at(w.cur, 0, 1) = Cell{};
    m = decideRabbit(w, w.cur, 0, 0, 0);
    CHECK(m.destY == 1 && m.hasChild && m.animal.procAge == 0);
}

static void testFoxDecisions() {
    World w;
    initWorld(w, 2, 3, 1, 3);
    w.at(w.cur, 0, 1) = make(FOX, 0, 2);
    // Would reach GEN_FOOD_FOXES with no rabbit next to it: dies before moving.
    CHECK(!decideFox(w, w.cur, 0, 0, 1).alive);
    // Below the limit it moves and gets hungrier.
    w.at(w.cur, 0, 1) = make(FOX, 0, 1);
    Move m = decideFox(w, w.cur, 0, 0, 1);
    CHECK(m.alive && m.animal.foodAge == 2 && m.animal.procAge == 1);
    // A rabbit saves it, is preferred over empty cells, and resets its hunger.
    w.at(w.cur, 0, 1) = make(FOX, 0, 2);
    w.at(w.cur, 0, 2) = make(RABBIT, 0, 0);
    m = decideFox(w, w.cur, 0, 0, 1);
    CHECK(m.alive && m.destY == 2 && m.animal.foodAge == 0);
    // Procreating without eating: the parent keeps its hunger and the child starts at 0.
    w.at(w.cur, 0, 2) = Cell{};
    w.at(w.cur, 0, 1) = make(FOX, 2, 1);
    m = decideFox(w, w.cur, 0, 0, 1);
    CHECK(m.hasChild && m.animal.procAge == 0 && m.animal.foodAge == 2);
    applyFoxMove(w, w.next, m, 0, 1);
    CHECK(same(w.at(w.next, 0, 1), make(FOX, 0, 0)));
}

// Carrying is what keeps a rabbit from overwriting a fox that arrived first, in any order.
static void testCarryRules() {
    const Cell rock = make(ROCK, 0, 0);
    const Cell fox = make(FOX, 2, 1);
    const Cell rabbit = make(RABBIT, 3, 0);

    Cell d{};
    carryRabbitSubphase(d, rock);
    CHECK(same(d, rock));
    d = Cell{};
    carryRabbitSubphase(d, fox);
    CHECK(same(d, fox));
    d = Cell{};
    carryRabbitSubphase(d, Cell{});
    CHECK(d.kind == EMPTY);

    d = Cell{};
    carryFoxSubphase(d, rock);
    CHECK(same(d, rock));
    d = Cell{};
    carryFoxSubphase(d, rabbit);
    CHECK(same(d, rabbit));
    d = fox;
    carryFoxSubphase(d, rabbit);
    CHECK(same(d, fox));
    d = Cell{};
    carryFoxSubphase(d, rabbit);
    mergeFox(d, fox);
    CHECK(same(d, fox));
}

static void checkBands(int rows, int threads) {
    Band bands[64];
    staticBands(rows, threads, bands);
    int next = 0, largest = 0, smallest = rows;
    for (int t = 0; t < threads; t++) {
        CHECK(bands[t].first == next);
        CHECK(bands[t].last >= bands[t].first);
        next = bands[t].last;
        const int size = bands[t].last - bands[t].first;
        if (size > largest) largest = size;
        if (size < smallest) smallest = size;
    }
    CHECK(next == rows);
    CHECK(largest - smallest <= 1);

    int owner[512];
    fillRowOwners(bands, threads, owner);
    for (int t = 0; t < threads; t++)
        for (int x = bands[t].first; x < bands[t].last; x++) CHECK(owner[x] == t);
}

static void testStaticBands() {
    checkBands(5, 16);
    checkBands(100, 1);
    checkBands(100, 8);
    checkBands(101, 8);
    checkBands(16, 16);
    checkBands(1, 2);
    Band three[3];
    staticBands(2, 3, three);
    CHECK(three[2].first == three[2].last);
}

// Bands cut at arbitrary points, with empty ones anywhere, must also work.
static void testRowOwnersWithUnevenBands() {
    const Band bands[4] = {{0, 0}, {0, 3}, {3, 3}, {3, 4}};
    int owner[4];
    fillRowOwners(bands, 4, owner);
    CHECK(owner[0] == 1 && owner[1] == 1 && owner[2] == 1 && owner[3] == 3);
}

static long long bandCost(const int* cost, const Band& band) {
    long long sum = 0;
    for (int x = band.first; x < band.last; x++) sum += cost[x];
    return sum;
}

// The largest band, which is what limits the time of a generation.
static long long largestBand(const int* cost, const Band* bands, int threads) {
    long long largest = 0;
    for (int t = 0; t < threads; t++) {
        const long long c = bandCost(cost, bands[t]);
        if (c > largest) largest = c;
    }
    return largest;
}

static void checkCoversAll(const Band* bands, int rows, int threads) {
    int next = 0;
    for (int t = 0; t < threads; t++) {
        CHECK(bands[t].first == next);
        CHECK(bands[t].last >= bands[t].first);
        next = bands[t].last;
    }
    CHECK(next == rows);
}

static void testAdaptiveBandsEqualizeCost() {
    // All the load in the first 8 rows of 64: static gives thread 0 all of it.
    int cost[64];
    for (int x = 0; x < 64; x++) cost[x] = x < 8 ? 1000 : 10;
    Band adaptive[4], fixed[4];
    adaptiveBands(cost, 64, 4, adaptive);
    staticBands(64, 4, fixed);
    checkCoversAll(adaptive, 64, 4);
    CHECK(adaptive[0].last - adaptive[0].first < 8);
    CHECK(largestBand(cost, adaptive, 4) * 2 < largestBand(cost, fixed, 4));

    // Uniform cost: as even as possible.
    for (int x = 0; x < 64; x++) cost[x] = 7;
    adaptiveBands(cost, 64, 4, adaptive);
    checkCoversAll(adaptive, 64, 4);
    for (int t = 0; t < 4; t++) CHECK(adaptive[t].last - adaptive[t].first == 16);
}

static void testAdaptiveBandsDegenerateInputs() {
    // A heavy row takes a band for itself and the rest share what remains.
    const int heavyFirst[6] = {100, 1, 1, 1, 1, 1};
    Band three[3];
    adaptiveBands(heavyFirst, 6, 3, three);
    checkCoversAll(three, 6, 3);
    CHECK(three[0].last == 1);
    CHECK(three[1].last - three[1].first >= 2 && three[2].last - three[2].first >= 2);

    const int heavyLast[6] = {1, 1, 1, 1, 1, 100};
    adaptiveBands(heavyLast, 6, 3, three);
    checkCoversAll(three, 6, 3);
    CHECK(three[2].first == 5);

    // As many threads as rows: one row each, whatever the costs.
    Band six[6];
    adaptiveBands(heavyFirst, 6, 6, six);
    checkCoversAll(six, 6, 6);
    for (int t = 0; t < 6; t++) CHECK(six[t].last - six[t].first == 1);

    // More threads than rows: one row each and the last ones empty, as in staticBands.
    Band many[16];
    adaptiveBands(heavyFirst, 6, 16, many);
    checkCoversAll(many, 6, 16);
    for (int t = 0; t < 16; t++) CHECK(many[t].last - many[t].first == (t < 6 ? 1 : 0));

    Band one[1];
    adaptiveBands(heavyFirst, 6, 1, one);
    CHECK(one[0].first == 0 && one[0].last == 6);

    // No load at all: nothing to follow, so an even split.
    const int zero[6] = {0, 0, 0, 0, 0, 0};
    Band two[2];
    adaptiveBands(zero, 6, 2, two);
    CHECK(two[0].first == 0 && two[0].last == 3 && two[1].first == 3 && two[1].last == 6);

    // Zero cost rows mixed with a cost that does not reach overflow when added up.
    const int big[4] = {INT_MAX, 0, INT_MAX, INT_MAX};
    Band pair[2];
    adaptiveBands(big, 4, 2, pair);
    checkCoversAll(pair, 4, 2);
    CHECK(bandCost(big, pair[0]) > 0 && bandCost(big, pair[1]) > 0);
}

static void testRowCosts() {
    World w;
    initWorld(w, 3, 3, 3, 4);
    w.at(w.cur, 0, 0) = make(RABBIT, 0, 0);
    w.at(w.cur, 0, 3) = make(FOX, 0, 0);
    w.at(w.cur, 1, 2) = make(ROCK, 0, 0);
    w.at(w.cur, 2, 1) = make(RABBIT, 0, 0);
    int cost[3] = {-1, -1, -1};
    fillRowCosts(w, w.cur, Band{0, 2}, 10, cost);
    CHECK(cost[0] == 4 + 2 * 10);  // Animals of both kinds count.
    CHECK(cost[1] == 4);           // A rock does not.
    CHECK(cost[2] == -1);          // Outside the band: untouched.
    fillRowCosts(w, w.cur, Band{0, 1}, INT_MAX, cost);
    CHECK(cost[0] == INT_MAX);     // Saturates instead of overflowing.
}

static void testMoveBoxGrowsWithoutLosingElements() {
    MoveBox box{};
    CHECK(box.items == nullptr && box.count == 0 && box.capacity == 0);
    const int total = 100000;
    int lastCapacity = 0;
    int growths = 0;
    for (int i = 0; i < total; i++) {
        pushMove(box, i, -i, make(FOX, i, i + 1));
        if (box.capacity != lastCapacity) {
            lastCapacity = box.capacity;
            growths++;
        }
        CHECK(box.count == i + 1);
        CHECK(box.capacity >= box.count);
    }
    CHECK(growths > 1);
    bool intact = true;
    for (int i = 0; i < total; i++) {
        const MoveBox::Move& m = box.items[i];
        intact = intact && m.x == i && m.y == -i && same(m.cell, make(FOX, i, i + 1));
    }
    CHECK(intact);

    // Capacity is kept between uses.
    const int capacity = box.capacity;
    box.count = 0;
    pushMove(box, 7, 8, make(RABBIT, 1, 0));
    CHECK(box.capacity == capacity && box.count == 1 && box.items[0].x == 7);
    freeMoveBox(box);
    CHECK(box.items == nullptr && box.count == 0 && box.capacity == 0);
}

int main() {
    testMergeOrderIndependence();
    testMergeWinners();
    testChooseCell();
    testProcreatingRabbitLosesConflict();
    testAgeHasNoCap();
    testFoxDecisions();
    testCarryRules();
    testStaticBands();
    testRowOwnersWithUnevenBands();
    testAdaptiveBandsEqualizeCost();
    testAdaptiveBandsDegenerateInputs();
    testRowCosts();
    testMoveBoxGrowsWithoutLosingElements();
    if (failures) printf("%d failures\n", failures);
    return failures ? 1 : 0;
}
