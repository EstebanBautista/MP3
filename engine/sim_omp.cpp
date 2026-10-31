// OpenMP simulation with row bands that follow the load.
//
// Same passes and same synchronization as sim_pth.cpp, see bands.hpp and that file: a parallel region
// is the team of persistent threads, and each pass ends in an explicit barrier. A parallel for would
// not fit, since bands and boxes are not iterations of a loop.
//
// With --schedule adaptive the bands are cut again every REBALANCE_EVERY generations, between
// generations, when every box is empty and no thread is using the old bands. Each thread estimates
// the cost of the rows it owns, and after a barrier thread 0 makes the cuts, which the others see
// after another one. New bands only change which thread computes each cell, and w.next is cleared by
// its new owner, so the result does not depend on them. --schedule static never moves them, which
// makes it the control for comparing the partition without changing the threading model.
#include <omp.h>

#include <cstring>

#include "bands.hpp"
#include "simulator.hpp"

namespace {

struct Team {
    BandPlan plan;
    Band* bands;     // Same array as plan.bands, for thread 0 to change.
    int* rowOwner;   // Same array as plan.rowOwner, for thread 0 to change.
    int* rowCost;
    Observer* obs;
    double* busy;    // Seconds of each thread outside barriers and the observer. Written at the end.
    bool adaptive;
};

void rebalance(Team& team, int id, Stopwatch& busy) {
    const World& w = *team.plan.w;
    busy.start();
    fillRowCosts(w, w.cur, team.plan.bands[id], OmpSimulator::ANIMAL_WEIGHT, team.rowCost);
    busy.stop();
#pragma omp barrier
    if (id == 0) {
        busy.start();
        adaptiveBands(team.rowCost, w.cfg.rows, team.plan.threads, team.bands);
        fillRowOwners(team.bands, team.plan.threads, team.rowOwner);
        busy.stop();
    }
#pragma omp barrier
}

void simulate(Team& team, int id) {
    const BandPlan& plan = team.plan;
    World& w = *plan.w;
    Stopwatch busy;
    for (int gen = 0; gen < w.cfg.nGen; gen++) {
        if (team.adaptive && gen % OmpSimulator::REBALANCE_EVERY == 0) rebalance(team, id, busy);

        busy.start();
        rabbitLocalPass(plan, id, gen, w.cur, w.next);
        busy.stop();
#pragma omp barrier
        busy.start();
        inboundPass<mergeRabbit>(plan, id, w.next);
        busy.stop();
#pragma omp barrier

        busy.start();
        foxLocalPass(plan, id, gen, w.next, w.cur);
        busy.stop();
#pragma omp barrier
        busy.start();
        inboundPass<mergeFox>(plan, id, w.cur);
        busy.stop();
#pragma omp barrier

        if (team.obs) {
            if (id == 0) team.obs->onGeneration(gen + 1, w);
#pragma omp barrier
        }
    }
    team.busy[id] = busy.seconds();
}

}  // namespace

OmpSimulator::~OmpSimulator() {
    delete[] bands_;
    delete[] rowOwner_;
}

bool OmpSimulator::setExtraOption(const char* value) {
    if (!strcmp(value, "adaptive")) adaptive_ = true;
    else if (!strcmp(value, "static")) adaptive_ = false;
    else return false;
    return true;
}

void OmpSimulator::run(World& w, int threads, Observer* obs) {
    const size_t boxCount = (size_t)threads * threads;
    delete[] bands_;
    bands_ = allocateArray<Band>(threads);
    delete[] rowOwner_;
    rowOwner_ = allocateArray<int>(w.cfg.rows);
    int* rowCost = allocateArray<int>(w.cfg.rows);
    MoveBox* boxes = allocateArray<MoveBox>(boxCount);
    double* busy = allocateArray<double>(threads);

    Team team{BandPlan{&w, threads, bands_, rowOwner_, boxes}, bands_, rowOwner_, rowCost, obs, busy,
              adaptive_};

    omp_set_dynamic(0);
#pragma omp parallel num_threads(threads)
    {
        // A team smaller than requested is still legal, so the first cut must wait to see it. A box
        // array for the request also fits it, since only the stride changes.
#pragma omp single
        {
            team.plan.threads = omp_get_num_threads();
            staticBands(w.cfg.rows, team.plan.threads, bands_);
            fillRowOwners(bands_, team.plan.threads, rowOwner_);
        }
        simulate(team, omp_get_thread_num());
    }

    team_ = team.plan.threads;
    imbalance_ = maxOverMean(busy, team_);

    for (size_t i = 0; i < boxCount; i++) freeMoveBox(boxes[i]);
    delete[] busy;
    delete[] boxes;
    delete[] rowCost;
}
