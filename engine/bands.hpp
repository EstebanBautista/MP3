// Partition of the grid in row bands and the mailboxes for moves that cross them. Independent of the
// threading library, so every band based simulator can share it.
#pragma once
#include <chrono>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <new>

#include "rules.hpp"
#include "world.hpp"

// Rows first..last-1 of the grid. Empty if first == last.
struct Band {
    int first;
    int last;
};

// Splits the rows in contiguous bands whose sizes differ by at most one. With more threads than
// rows, the last threads get empty bands.
inline void staticBands(int rows, int threads, Band* out) {
    const int base = rows / threads;
    const int extra = rows % threads;
    int next = 0;
    for (int t = 0; t < threads; t++) {
        out[t].first = next;
        next += base + (t < extra ? 1 : 0);
        out[t].last = next;
    }
}

// Cuts the rows in contiguous bands of similar total cost, walking the rows once. Each band takes
// rows while that brings it closer to an equal share of what remains, so the bands after a very
// heavy row share the rest evenly instead of paying for it. If there are enough rows no band is
// empty; if not, each row is a band and the last threads get empty ones, as in staticBands. With no
// cost at all there is nothing to follow, so the split is the static one. Costs must not be negative.
inline void adaptiveBands(const int* rowCost, int rows, int threads, Band* out) {
    long long remaining = 0;
    for (int x = 0; x < rows; x++) remaining += rowCost[x];
    if (remaining == 0) {
        staticBands(rows, threads, out);
        return;
    }
    int next = 0;
    for (int t = 0; t < threads; t++) {
        const int left = threads - t;
        out[t].first = next;
        if (left == 1) {
            next = rows;
        } else if (next < rows) {
            const int limit = rows - (left - 1);  // Keeps one row for each band after this one.
            const double share = (double)remaining / left;
            long long sum = rowCost[next++];
            while (next < limit &&
                   fabs((double)(sum + rowCost[next]) - share) < fabs((double)sum - share))
                sum += rowCost[next++];
            remaining -= sum;
        }
        out[t].last = next;
    }
}

// Estimated cost of simulating each row of the band: walking its cells, and a weight per animal for
// the decision and the delivery. Written to rowCost[x]. The sum saturates at INT_MAX.
inline void fillRowCosts(const World& w, const Cell* grid, const Band& band, int animalWeight,
                         int* rowCost) {
    const int cols = w.cfg.cols;
    for (int x = band.first; x < band.last; x++) {
        const Cell* row = &w.at(grid, x, 0);
        int animals = 0;
        for (int y = 0; y < cols; y++) animals += row[y].kind == RABBIT || row[y].kind == FOX;
        const long long cost = cols + (long long)animalWeight * animals;
        rowCost[x] = cost < INT_MAX ? (int)cost : INT_MAX;
    }
}

// Fills owner[x] with the thread whose band holds row x. The bands must cover every row exactly
// once, in any sizes.
inline void fillRowOwners(const Band* bands, int threads, int* owner) {
    for (int t = 0; t < threads; t++)
        for (int x = bands[t].first; x < bands[t].last; x++) owner[x] = t;
}

// Moves from one thread to another, one box per source and destination. A box is written only by
// its source and then read only by its destination, and the caller must separate both with a
// synchronization point, so nothing here locks. Aligned to a cache line so that the counters of
// different sources do not share one. Move is nested because rules.hpp has a global Move, what an
// animal decides, and this one is only a candidate for a cell.
struct alignas(64) MoveBox {
    struct Move {
        int x;
        int y;
        Cell cell;
    };
    Move* items;
    int count;
    int capacity;
};

// Appends a candidate, growing the box when full. Elements already stored are kept. There is no way
// to continue the run without memory, so running out of it ends the process.
inline void pushMove(MoveBox& box, int x, int y, const Cell& cell) {
    if (box.count == box.capacity) {
        const int capacity =
            box.capacity == 0 ? 64 : box.capacity <= INT_MAX / 2 ? box.capacity * 2 : INT_MAX;
        void* grown = box.capacity == INT_MAX
                          ? nullptr
                          : realloc(box.items, (size_t)capacity * sizeof(MoveBox::Move));
        if (!grown) {
            fputs("error: cannot allocate memory for moves between bands\n", stderr);
            exit(1);
        }
        box.items = static_cast<MoveBox::Move*>(grown);
        box.capacity = capacity;
    }
    box.items[box.count++] = MoveBox::Move{x, y, cell};
}

inline void freeMoveBox(MoveBox& box) {
    free(box.items);
    box.items = nullptr;
    box.count = 0;
    box.capacity = 0;
}

[[noreturn]] inline void fatal(const char* message) {
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

// Maximum busy time divided by the mean, 1 if nobody did anything.
inline double maxOverMean(const double* busy, int threads) {
    double total = 0.0, largest = 0.0;
    for (int t = 0; t < threads; t++) {
        total += busy[t];
        if (busy[t] > largest) largest = busy[t];
    }
    return total > 0.0 ? largest * threads / total : 1.0;
}

// What the two passes of a subphase share, whatever threads run them. Each subphase reads a grid no
// one writes and builds the other one, in two passes that the caller separates and follows with a
// synchronization point:
//   1. Local pass: each thread walks its band in the source grid. It clears and writes only cells of
//      its band in the destination grid. Moves that land in another band go to a MoveBox.
//   2. Inbound pass: each thread applies with merge* the boxes addressed to it, again writing only
//      its band, and empties them for the next subphase.
// No cell is written by two threads and no box is used by two threads at once, so the merges need no
// locks, and the merge rules make the result independent of the order of arrival.
struct BandPlan {
    World* w;
    int threads;
    const Band* bands;
    const int* rowOwner;
    MoveBox* boxes;  // threads * threads, indexed by source and then destination.
};

// Hands a candidate to its cell if the thread owns it, or to the box of the thread that does.
template <void Merge(Cell&, const Cell&)>
class BandSink {
public:
    BandSink(const BandPlan& plan, int id, Cell* dst) : plan_(plan), id_(id), dst_(dst) {}
    void operator()(int x, int y, const Cell& candidate) const {
        const Band& band = plan_.bands[id_];
        if (x >= band.first && x < band.last) {
            Merge(dst_[(size_t)x * plan_.w->cfg.cols + y], candidate);
        } else {
            const int owner = plan_.rowOwner[x];
            pushMove(plan_.boxes[(size_t)id_ * plan_.threads + owner], x, y, candidate);
        }
    }

private:
    const BandPlan& plan_;
    int id_;
    Cell* dst_;
};

inline void clearBand(const World& w, Cell* grid, const Band& band) {
    const size_t end = (size_t)band.last * w.cfg.cols;
    for (size_t i = (size_t)band.first * w.cfg.cols; i < end; i++) grid[i] = Cell{};
}

inline void rabbitLocalPass(const BandPlan& plan, int id, int gen, const Cell* src, Cell* dst) {
    const World& w = *plan.w;
    const Band& band = plan.bands[id];
    const BandSink<mergeRabbit> sink(plan, id, dst);
    clearBand(w, dst, band);
    for (int x = band.first; x < band.last; x++)
        for (int y = 0; y < w.cfg.cols; y++) {
            const Cell& c = w.at(src, x, y);
            if (c.kind == RABBIT) deliverRabbitMove(decideRabbit(w, src, gen, x, y), x, y, sink);
            else carryRabbitSubphase(dst[(size_t)x * w.cfg.cols + y], c);
        }
}

inline void foxLocalPass(const BandPlan& plan, int id, int gen, const Cell* src, Cell* dst) {
    const World& w = *plan.w;
    const Band& band = plan.bands[id];
    const BandSink<mergeFox> sink(plan, id, dst);
    clearBand(w, dst, band);
    for (int x = band.first; x < band.last; x++)
        for (int y = 0; y < w.cfg.cols; y++) {
            const Cell& c = w.at(src, x, y);
            if (c.kind == FOX) deliverFoxMove(decideFox(w, src, gen, x, y), x, y, sink);
            else carryFoxSubphase(dst[(size_t)x * w.cfg.cols + y], c);
        }
}

template <void Merge(Cell&, const Cell&)>
void inboundPass(const BandPlan& plan, int id, Cell* dst) {
    if (plan.bands[id].first == plan.bands[id].last) return;  // Nothing can land in an empty band.
    const int cols = plan.w->cfg.cols;
    for (int source = 0; source < plan.threads; source++) {
        MoveBox& box = plan.boxes[(size_t)source * plan.threads + id];
        for (int i = 0; i < box.count; i++) {
            const MoveBox::Move& m = box.items[i];
            Merge(dst[(size_t)m.x * cols + m.y], m.cell);
        }
        box.count = 0;
    }
}
