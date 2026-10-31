// World model: flat grids of cells, double buffered.
#pragma once
#include <cstddef>
#include <cstdint>

enum CellKind : uint8_t { EMPTY = 0, ROCK = 1, RABBIT = 2, FOX = 3 };

struct Cell {
    uint8_t kind;
    int32_t procAge;
    int32_t foodAge;
};

struct Config {
    int genProcRabbits, genProcFoxes, genFoodFoxes, nGen, rows, cols;
};

class World {
public:
    Config cfg{};
    Cell* cur = nullptr;
    Cell* next = nullptr;

    World() = default;
    ~World();
    World(const World&) = delete;
    World& operator=(const World&) = delete;

    // Allocates both grids (all EMPTY) for the given config. Returns false on bad size.
    bool init(const Config& c);
    // x is the row, y is the column.
    Cell& at(Cell* grid, int x, int y) { return grid[(size_t)x * cfg.cols + y]; }
    const Cell& at(const Cell* grid, int x, int y) const { return grid[(size_t)x * cfg.cols + y]; }
    void swapGrids();
};
