// Pthreads simulation with static row bands and persistent threads.
//
// Each subphase runs the passes of bands.hpp, separated by barriers:
//   1. Local pass.
//   2. Barrier. Now every box is complete and no one writes to it again.
//   3. Inbound pass.
//   4. Barrier. Now the destination grid is complete, so the next subphase can read it, and clear
//      the grid just read.
//
// The workers do not swap w.cur and w.next, which would be a shared write: the rabbit subphase goes
// from cur to next and the fox subphase from next to cur, leaving each generation in w.cur as the
// Observer expects.
//
// The observer runs on worker 0 after step 4 of the fox subphase, and the others wait for it in one
// more barrier. Without an observer that barrier is skipped.
#include <pthread.h>

#include "bands.hpp"
#include "simulator.hpp"

namespace {

struct Shared {
    BandPlan plan;
    Observer* obs;
    double* busy;  // Seconds of each worker outside barriers and the observer. Written at the end.
    pthread_barrier_t barrier;
};

struct Worker {
    Shared* shared;
    int id;
};

void* workerMain(void* arg) {
    Worker& self = *static_cast<Worker*>(arg);
    Shared& s = *self.shared;
    World& w = *s.plan.w;
    Stopwatch busy;
    for (int gen = 0; gen < w.cfg.nGen; gen++) {
        busy.start();
        rabbitLocalPass(s.plan, self.id, gen, w.cur, w.next);
        busy.stop();
        pthread_barrier_wait(&s.barrier);
        busy.start();
        inboundPass<mergeRabbit>(s.plan, self.id, w.next);
        busy.stop();
        pthread_barrier_wait(&s.barrier);

        busy.start();
        foxLocalPass(s.plan, self.id, gen, w.next, w.cur);
        busy.stop();
        pthread_barrier_wait(&s.barrier);
        busy.start();
        inboundPass<mergeFox>(s.plan, self.id, w.cur);
        busy.stop();
        pthread_barrier_wait(&s.barrier);

        if (s.obs) {
            if (self.id == 0) s.obs->onGeneration(gen + 1, w);
            pthread_barrier_wait(&s.barrier);
        }
    }
    s.busy[self.id] = busy.seconds();
    return nullptr;
}

}  // namespace

void PthSimulator::run(World& w, int threads, Observer* obs) {
    const size_t boxCount = (size_t)threads * threads;
    Band* bands = allocateArray<Band>(threads);
    int* rowOwner = allocateArray<int>(w.cfg.rows);
    MoveBox* boxes = allocateArray<MoveBox>(boxCount);
    double* busy = allocateArray<double>(threads);
    Worker* workers = allocateArray<Worker>(threads);
    pthread_t* handles = allocateArray<pthread_t>(threads);

    staticBands(w.cfg.rows, threads, bands);
    fillRowOwners(bands, threads, rowOwner);

    Shared shared{BandPlan{&w, threads, bands, rowOwner, boxes}, obs, busy, {}};
    if (pthread_barrier_init(&shared.barrier, nullptr, (unsigned)threads) != 0)
        fatal("cannot create the barrier");

    // The calling thread is worker 0.
    for (int t = 0; t < threads; t++) workers[t] = Worker{&shared, t};
    for (int t = 1; t < threads; t++)
        if (pthread_create(&handles[t], nullptr, workerMain, &workers[t]) != 0)
            fatal("cannot create the worker threads");
    workerMain(&workers[0]);
    for (int t = 1; t < threads; t++) pthread_join(handles[t], nullptr);

    imbalance_ = maxOverMean(busy, threads);

    pthread_barrier_destroy(&shared.barrier);
    for (size_t i = 0; i < boxCount; i++) freeMoveBox(boxes[i]);
    delete[] handles;
    delete[] workers;
    delete[] busy;
    delete[] boxes;
    delete[] rowOwner;
    delete[] bands;
}
