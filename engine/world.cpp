#include "world.hpp"

#include <new>
#include <utility>

World::~World() {
    delete[] cur;
    delete[] next;
}

bool World::init(const Config& c) {
    if (c.rows <= 0 || c.cols <= 0) return false;
    if ((long long)c.rows * c.cols > (1LL << 28)) return false;
    delete[] cur;
    delete[] next;
    cur = next = nullptr;
    cfg = c;
    size_t n = (size_t)c.rows * c.cols;
    cur = new (std::nothrow) Cell[n]();
    next = new (std::nothrow) Cell[n]();
    if (!cur || !next) {
        delete[] cur;
        delete[] next;
        cur = next = nullptr;
        return false;
    }
    return true;
}

void World::swapGrids() { std::swap(cur, next); }
