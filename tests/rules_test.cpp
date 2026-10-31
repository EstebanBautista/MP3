// Native tests of rules.hpp, run by tests/test_edge_cases.py. Exit code 0 means all passed.
#include <cstdio>

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

int main() {
    testMergeOrderIndependence();
    testMergeWinners();
    testChooseCell();
    testProcreatingRabbitLosesConflict();
    testAgeHasNoCap();
    testFoxDecisions();
    if (failures) printf("%d failures\n", failures);
    return failures ? 1 : 0;
}
