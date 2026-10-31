// Pthreads simulation with static row bands and persistent threads.
//
// Each subphase reads a grid no one writes and builds the other one, in two steps:
//   1. Local pass: each worker walks its band in the source grid. It clears and writes only cells of
//      its band in the destination grid. Moves that land in another band go to a MoveBox.
//   2. Barrier. Now every box is complete and no one writes to it again.
//   3. Inbound pass: each worker applies with merge* the boxes addressed to it, again writing only
//      its band, and empties them for the next subphase.
//   4. Barrier. Now the destination grid is complete, so the next subphase can read it, and clear
//      the grid just read.
//
// No cell is written by two threads and no box is used by two threads at once, so the merges need no
// locks, and the merge rules make the result independent of the order of arrival. The workers do not
// swap w.cur and w.next, which would be a shared write: the rabbit subphase goes from cur to next and
// the fox subphase from next to cur, leaving each generation in w.cur as the Observer expects.
//
// The observer runs on worker 0 after step 4 of the fox subphase, and the others wait for it in one
// more barrier. Without an observer that barrier is skipped.
#include <pthread.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <new>

#include "bands.hpp"
#include "rules.hpp"
#include "simulator.hpp"

namespace {

[[noreturn]] void fatal(const char* message) {
    fprintf(stderr, "error: %s\n", message);
    exit(1);
}

// A zeroed array. The aligned form of operator new honors the cache line alignment of MoveBox.
template <typename T>
T* allocateArray(size_t n) {
    T* p = new (std::nothrow) T[n]();
    if (!p) fatal("cannot allocate memory for the threads");
    return p;
}

struct Shared {
    World* w;
    Observer* obs;
    int threads;
    const Band* bands;
    const int* rowOwner;
    MoveBox* boxes;  // threads * threads, indexed by source and then destination.
    pthread_barrier_t barrier;
};

struct Worker {
    Shared* shared;
    int id;
    double busy;  // Seconds of the worker outside barriers and the observer. Written at the end.
};

class Stopwatch {
public:
    void start() { begin_ = std::chrono::steady_clock::now(); }
    void stop() {
        seconds_ += std::chrono::duration<double>(std::chrono::steady_clock::now() - begin_).count();
    }
    double seconds() const { return seconds_; }

private:
    std::chrono::steady_clock::time_point begin_;
    double seconds_ = 0.0;
};

// What the local pass of a worker needs to deliver a candidate to its cell.
struct Outbox {
    Shared& s;
    int id;
    Cell* dst;
    const Band& band;
};

template <void Merge(Cell&, const Cell&)>
void deliver(Outbox& out, int x, int y, const Cell& candidate) {
    const World& w = *out.s.w;
    if (x >= out.band.first && x < out.band.last) {
        Merge(out.dst[(size_t)x * w.cfg.cols + y], candidate);
    } else {
        const int owner = out.s.rowOwner[x];
        pushMove(out.s.boxes[(size_t)out.id * out.s.threads + owner], x, y, candidate);
    }
}

void clearBand(const World& w, Cell* grid, const Band& band) {
    const size_t end = (size_t)band.last * w.cfg.cols;
    for (size_t i = (size_t)band.first * w.cfg.cols; i < end; i++) grid[i] = Cell{};
}

void rabbitLocalPass(Shared& s, int id, int gen, const Cell* src, Cell* dst) {
    const World& w = *s.w;
    const Band& band = s.bands[id];
    Outbox out{s, id, dst, band};
    clearBand(w, dst, band);
    for (int x = band.first; x < band.last; x++)
        for (int y = 0; y < w.cfg.cols; y++) {
            const Cell& c = w.at(src, x, y);
            if (c.kind == RABBIT) {
                const Move m = decideRabbit(w, src, gen, x, y);
                deliver<mergeRabbit>(out, m.destX, m.destY, m.animal);
                if (m.hasChild) deliver<mergeRabbit>(out, x, y, newborn(RABBIT));
            } else {
                carryRabbitSubphase(dst[(size_t)x * w.cfg.cols + y], c);
            }
        }
}

void foxLocalPass(Shared& s, int id, int gen, const Cell* src, Cell* dst) {
    const World& w = *s.w;
    const Band& band = s.bands[id];
    Outbox out{s, id, dst, band};
    clearBand(w, dst, band);
    for (int x = band.first; x < band.last; x++)
        for (int y = 0; y < w.cfg.cols; y++) {
            const Cell& c = w.at(src, x, y);
            if (c.kind == FOX) {
                const Move m = decideFox(w, src, gen, x, y);
                if (!m.alive) continue;
                deliver<mergeFox>(out, m.destX, m.destY, m.animal);
                if (m.hasChild) deliver<mergeFox>(out, x, y, newborn(FOX));
            } else {
                carryFoxSubphase(dst[(size_t)x * w.cfg.cols + y], c);
            }
        }
}

template <void Merge(Cell&, const Cell&)>
void inboundPass(Shared& s, int id, Cell* dst) {
    if (s.bands[id].first == s.bands[id].last) return;  // Nothing can land in an empty band.
    const int cols = s.w->cfg.cols;
    for (int source = 0; source < s.threads; source++) {
        MoveBox& box = s.boxes[(size_t)source * s.threads + id];
        for (int i = 0; i < box.count; i++) {
            const MoveBox::Move& m = box.items[i];
            Merge(dst[(size_t)m.x * cols + m.y], m.cell);
        }
        box.count = 0;
    }
}

void* workerMain(void* arg) {
    Worker& self = *static_cast<Worker*>(arg);
    Shared& s = *self.shared;
    World& w = *s.w;
    Stopwatch busy;
    for (int gen = 0; gen < w.cfg.nGen; gen++) {
        busy.start();
        rabbitLocalPass(s, self.id, gen, w.cur, w.next);
        busy.stop();
        pthread_barrier_wait(&s.barrier);
        busy.start();
        inboundPass<mergeRabbit>(s, self.id, w.next);
        busy.stop();
        pthread_barrier_wait(&s.barrier);

        busy.start();
        foxLocalPass(s, self.id, gen, w.next, w.cur);
        busy.stop();
        pthread_barrier_wait(&s.barrier);
        busy.start();
        inboundPass<mergeFox>(s, self.id, w.cur);
        busy.stop();
        pthread_barrier_wait(&s.barrier);

        if (s.obs) {
            if (self.id == 0) s.obs->onGeneration(gen + 1, w);
            pthread_barrier_wait(&s.barrier);
        }
    }
    self.busy = busy.seconds();
    return nullptr;
}

double maxOverMean(const Worker* workers, int threads) {
    double total = 0.0, largest = 0.0;
    for (int t = 0; t < threads; t++) {
        total += workers[t].busy;
        if (workers[t].busy > largest) largest = workers[t].busy;
    }
    return total > 0.0 ? largest * threads / total : 1.0;
}

}  // namespace

void PthSimulator::run(World& w, int threads, Observer* obs) {
    const size_t boxCount = (size_t)threads * threads;
    Band* bands = allocateArray<Band>(threads);
    int* rowOwner = allocateArray<int>(w.cfg.rows);
    MoveBox* boxes = allocateArray<MoveBox>(boxCount);
    Worker* workers = allocateArray<Worker>(threads);
    pthread_t* handles = allocateArray<pthread_t>(threads);

    staticBands(w.cfg.rows, threads, bands);
    fillRowOwners(bands, threads, rowOwner);

    Shared shared{&w, obs, threads, bands, rowOwner, boxes, {}};
    if (pthread_barrier_init(&shared.barrier, nullptr, (unsigned)threads) != 0)
        fatal("cannot create the barrier");

    // The calling thread is worker 0.
    for (int t = 0; t < threads; t++) workers[t] = Worker{&shared, t, 0.0};
    for (int t = 1; t < threads; t++)
        if (pthread_create(&handles[t], nullptr, workerMain, &workers[t]) != 0)
            fatal("cannot create the worker threads");
    workerMain(&workers[0]);
    for (int t = 1; t < threads; t++) pthread_join(handles[t], nullptr);

    imbalance_ = maxOverMean(workers, threads);

    pthread_barrier_destroy(&shared.barrier);
    for (size_t i = 0; i < boxCount; i++) freeMoveBox(boxes[i]);
    delete[] handles;
    delete[] workers;
    delete[] boxes;
    delete[] rowOwner;
    delete[] bands;
}
