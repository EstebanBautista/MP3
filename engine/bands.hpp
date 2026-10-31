// Partition of the grid in row bands and the mailboxes for moves that cross them. Independent of the
// threading library, so every band based simulator can share it.
#pragma once
#include <climits>
#include <cstdio>
#include <cstdlib>

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
