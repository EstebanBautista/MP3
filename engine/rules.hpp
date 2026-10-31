// Simulation rules for one animal in one subphase, shared by every simulator.
//
// A generation has two subphases, rabbits and then foxes, both using the number of the generation
// being computed (0 for the first). Each subphase reads only the state left by the previous one
// and writes a new grid, so cells freed during a subphase are not candidates. A simulator calls
// decideRabbit/decideFox for each animal, with no shared writes, and delivers the result with
// mergeRabbit/mergeFox in any order, synchronizing only the access to cells it shares.
//
// Decisions taken from the allgen example files. All of them reproduce allgen5x5, allgen10x10,
// allgen20x20 and allgen100x100 (10001 generations), and the 7 final outputs, byte for byte.
//
// - Ages have no cap. A rabbit that cannot move keeps aging past GEN_PROC_RABBITS: allgen20x20
//   shows age 4 with GEN_PROC_RABBITS=3 (generation 836, cell (0,17)), and allgen100x100 shows
//   age 7 with the same limit (generation 2527, cell (98,0)). Capping fails allgen20x20 at
//   generation 836. A cap would only change the displayed value: an animal above the limit that
//   moves is reset to 0, so it never reaches a conflict with its high age. Numbers print in full
//   with no padding, so a two-digit value widens its row.
//
// - Conflicts compare the procreation age after the move, so after the procreation reset. A rabbit
//   that procreates arrives with age 0 and loses to one that did not. Comparing before the reset
//   fails allgen20x20 at generation 870, allgen100x100 at generation 1453, and the 4 largest final
//   outputs. The two orders disagree in 3 rabbit conflicts of 20x20 and 5135 of 100x100.
//
// - For foxes the examples do not decide this. In the 7 cases, 0 of the fox conflicts rank the two
//   candidates differently before and after the reset, and both versions match every file. Foxes
//   use the same rule as rabbits, for consistency.
//
// - Hunger before or after eating cannot change the result. Foxes that meet in a cell saw the same
//   cell, so either all of them ate or none did. If all ate, the survivors of an age tie have
//   hunger 0 and are identical. If none ate, adding 1 to each keeps their order. This code compares
//   the hunger after the move.
//
// - Starvation is checked with the hunger the fox would reach: a fox with no adjacent rabbit dies
//   when hunger + 1 >= GEN_FOOD_FOXES, before moving, so hunger is never displayed at that value.
//   With GEN_FOOD_FOXES=3, hunger is 2 in generation 4 of allgen5x5 and the fox is gone in 5.
//
// - A new animal has both ages at 0, also a fox whose parent did not eat and has hunger above 0.
// - The limit is age >= GEN_PROC, so an animal past it procreates on the first move it can make.
#pragma once
#include "world.hpp"

// Only valid with p > 0.
inline int chooseCell(int gen, int x, int y, int p) { return (gen + x + y) % p; }

// Finds the neighbor of (x,y) chosen by the common criterion among those of the given kind, in
// north, east, south, west order. Returns false if there are none.
inline bool chooseNeighbor(const World& w, const Cell* grid, int gen, int x, int y, uint8_t kind,
                           int& destX, int& destY) {
    int cx[4], cy[4];
    int p = 0;
    if (x > 0 && w.at(grid, x - 1, y).kind == kind) {
        cx[p] = x - 1;
        cy[p++] = y;
    }
    if (y + 1 < w.cfg.cols && w.at(grid, x, y + 1).kind == kind) {
        cx[p] = x;
        cy[p++] = y + 1;
    }
    if (x + 1 < w.cfg.rows && w.at(grid, x + 1, y).kind == kind) {
        cx[p] = x + 1;
        cy[p++] = y;
    }
    if (y > 0 && w.at(grid, x, y - 1).kind == kind) {
        cx[p] = x;
        cy[p++] = y - 1;
    }
    if (p == 0) return false;
    const int k = chooseCell(gen, x, y, p);
    destX = cx[k];
    destY = cy[k];
    return true;
}

// What one animal does in its subphase.
struct Move {
    bool alive;     // False if the fox starved: nothing to deliver.
    int destX;      // Where `animal` goes, which is its own cell if it stays.
    int destY;
    Cell animal;    // The animal with its ages already updated.
    bool hasChild;  // A new animal of the same kind appears in the cell that was left.
};

// Merge a candidate into a cell of the new grid. The result does not depend on the order: animals
// of a kind have a total order by their ages, and candidates that tie are identical. A fox always
// replaces a rabbit, whichever is delivered first.
inline void mergeRabbit(Cell& dst, const Cell& candidate) {
    if (dst.kind == EMPTY || (dst.kind == RABBIT && candidate.procAge > dst.procAge))
        dst = candidate;
}

inline void mergeFox(Cell& dst, const Cell& candidate) {
    if (dst.kind != FOX || candidate.procAge > dst.procAge ||
        (candidate.procAge == dst.procAge && candidate.foodAge < dst.foodAge))
        dst = candidate;
}

// Applies the procreation rule to an animal that has already set its other fields.
inline void updateProcreation(Move& m, int oldAge, bool moved, int genProc) {
    if (moved && oldAge >= genProc) {
        m.animal.procAge = 0;
        m.hasChild = true;
    } else {
        m.animal.procAge = oldAge + 1;
    }
}

// `grid` is the state at the start of the rabbit subphase, and (x,y) must hold a rabbit.
inline Move decideRabbit(const World& w, const Cell* grid, int gen, int x, int y) {
    const Cell& rabbit = w.at(grid, x, y);
    Move m{true, x, y, rabbit, false};
    const bool moved = chooseNeighbor(w, grid, gen, x, y, EMPTY, m.destX, m.destY);
    updateProcreation(m, rabbit.procAge, moved, w.cfg.genProcRabbits);
    return m;
}

// `grid` is the state at the start of the fox subphase, and (x,y) must hold a fox.
inline Move decideFox(const World& w, const Cell* grid, int gen, int x, int y) {
    const Cell& fox = w.at(grid, x, y);
    Move m{true, x, y, fox, false};
    bool moved = chooseNeighbor(w, grid, gen, x, y, RABBIT, m.destX, m.destY);
    if (moved) {
        m.animal.foodAge = 0;
    } else {
        if (fox.foodAge + 1 >= w.cfg.genFoodFoxes) {
            m.alive = false;
            return m;
        }
        m.animal.foodAge = fox.foodAge + 1;
        moved = chooseNeighbor(w, grid, gen, x, y, EMPTY, m.destX, m.destY);
    }
    updateProcreation(m, fox.procAge, moved, w.cfg.genProcFoxes);
    return m;
}

// The newborn of a kind.
inline Cell newborn(uint8_t kind) {
    Cell c{};
    c.kind = kind;
    return c;
}

// What each cell of the old grid leaves in the new one when it holds an animal that does not act in
// the subphase. Rocks and foxes never compete with a rabbit for a cell in the rabbit subphase, since
// rabbits only move to empty cells, so they are copied.
inline void carryRabbitSubphase(Cell& dst, const Cell& c) {
    if (c.kind == ROCK || c.kind == FOX) dst = c;
}

// A surviving rabbit goes through mergeRabbit because a fox may have eaten it already: this way it
// can never overwrite that fox, whichever is delivered first.
inline void carryFoxSubphase(Cell& dst, const Cell& c) {
    if (c.kind == RABBIT) mergeRabbit(dst, c);
    else if (c.kind == ROCK) dst = c;
}

// Delivery of a whole move, one candidate at a time, to whatever `sink(x, y, cell)` does with it. The
// child's cell is the one the parent left, which no other animal can target in this subphase.
template <typename Sink>
inline void deliverRabbitMove(const Move& m, int x, int y, Sink&& sink) {
    sink(m.destX, m.destY, m.animal);
    if (m.hasChild) sink(x, y, newborn(RABBIT));
}

template <typename Sink>
inline void deliverFoxMove(const Move& m, int x, int y, Sink&& sink) {
    if (!m.alive) return;
    sink(m.destX, m.destY, m.animal);
    if (m.hasChild) sink(x, y, newborn(FOX));
}

// Delivery to the new grid, for callers with no cell shared between threads.
inline void applyRabbitMove(const World& w, Cell* dst, const Move& m, int x, int y) {
    deliverRabbitMove(m, x, y, [&](int destX, int destY, const Cell& c) {
        mergeRabbit(dst[(size_t)destX * w.cfg.cols + destY], c);
    });
}

inline void applyFoxMove(const World& w, Cell* dst, const Move& m, int x, int y) {
    deliverFoxMove(m, x, y, [&](int destX, int destY, const Cell& c) {
        mergeFox(dst[(size_t)destX * w.cfg.cols + destY], c);
    });
}
