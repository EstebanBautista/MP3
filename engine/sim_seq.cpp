// Exact sequential simulation, the reference for all parallel versions.
#include "rules.hpp"
#include "simulator.hpp"

namespace {

void clearGrid(const World& w, Cell* grid) {
    const size_t total = (size_t)w.cfg.rows * w.cfg.cols;
    for (size_t i = 0; i < total; i++) grid[i] = Cell{};
}

void rabbitSubphase(World& w, int gen) {
    clearGrid(w, w.next);
    for (int x = 0; x < w.cfg.rows; x++)
        for (int y = 0; y < w.cfg.cols; y++) {
            const Cell& c = w.at(w.cur, x, y);
            if (c.kind == RABBIT) applyRabbitMove(w, w.next, decideRabbit(w, w.cur, gen, x, y), x, y);
            else carryRabbitSubphase(w.at(w.next, x, y), c);
        }
    w.swapGrids();
}

void foxSubphase(World& w, int gen) {
    clearGrid(w, w.next);
    for (int x = 0; x < w.cfg.rows; x++)
        for (int y = 0; y < w.cfg.cols; y++) {
            const Cell& c = w.at(w.cur, x, y);
            if (c.kind == FOX) applyFoxMove(w, w.next, decideFox(w, w.cur, gen, x, y), x, y);
            else carryFoxSubphase(w.at(w.next, x, y), c);
        }
    w.swapGrids();
}

}  // namespace

void SeqSimulator::run(World& w, int, Observer* obs) {
    for (int gen = 0; gen < w.cfg.nGen; gen++) {
        rabbitSubphase(w, gen);
        foxSubphase(w, gen);
        if (obs) obs->onGeneration(gen + 1, w);
    }
}
