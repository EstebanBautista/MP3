#include "io.hpp"

#include <cstring>

static bool fail(char* err, size_t errLen, const char* fmt, long a = 0) {
    if (err && errLen) snprintf(err, errLen, fmt, a);
    return false;
}

static const char* kindName(uint8_t k) {
    switch (k) {
        case ROCK: return "ROCK";
        case RABBIT: return "RABBIT";
        case FOX: return "FOX";
        default: return nullptr;
    }
}

bool readWorld(FILE* f, World& w, char* err, size_t errLen) {
    Config c;
    int n = 0;
    // %d skips any whitespace, so CRLF line endings are accepted.
    if (fscanf(f, "%d %d %d %d %d %d %d", &c.genProcRabbits, &c.genProcFoxes, &c.genFoodFoxes,
               &c.nGen, &c.rows, &c.cols, &n) != 7)
        return fail(err, errLen, "invalid or incomplete header");
    if (c.rows <= 0 || c.cols <= 0 || c.nGen < 0 || n < 0 || c.genProcRabbits < 0 ||
        c.genProcFoxes < 0 || c.genFoodFoxes < 0)
        return fail(err, errLen, "invalid header values");
    if ((long long)n > (long long)c.rows * c.cols)
        return fail(err, errLen, "more objects than cells (N=%ld)", n);
    if (!w.init(c)) return fail(err, errLen, "cannot allocate world");

    for (int i = 0; i < n; i++) {
        char name[32];
        int x, y;
        if (fscanf(f, "%31s %d %d", name, &x, &y) != 3)
            return fail(err, errLen, "too few object lines, found only %ld", i);
        uint8_t kind;
        if (!strcmp(name, "ROCK")) kind = ROCK;
        else if (!strcmp(name, "RABBIT")) kind = RABBIT;
        else if (!strcmp(name, "FOX")) kind = FOX;
        else return fail(err, errLen, "unknown object at line %ld", i + 2);
        if (x < 0 || x >= c.rows || y < 0 || y >= c.cols)
            return fail(err, errLen, "coordinates out of range at line %ld", i + 2);
        Cell& cell = w.at(w.cur, x, y);
        if (cell.kind != EMPTY) return fail(err, errLen, "duplicate cell at line %ld", i + 2);
        cell.kind = kind;
    }
    char extra[8];
    if (fscanf(f, "%7s", extra) == 1)
        return fail(err, errLen, "more objects than declared N=%ld", n);
    return true;
}

void writeWorld(FILE* f, const World& w) {
    const Config& c = w.cfg;
    size_t total = (size_t)c.rows * c.cols;
    int n = 0;
    for (size_t i = 0; i < total; i++) n += w.cur[i].kind != EMPTY;
    fprintf(f, "%d %d %d 0 %d %d %d\n", c.genProcRabbits, c.genProcFoxes, c.genFoodFoxes, c.rows,
            c.cols, n);
    for (int x = 0; x < c.rows; x++)
        for (int y = 0; y < c.cols; y++) {
            const char* name = kindName(w.at(w.cur, x, y).kind);
            if (name) fprintf(f, "%s %d %d\n", name, x, y);
        }
}
