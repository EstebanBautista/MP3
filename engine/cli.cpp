#include "cli.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

#include "io.hpp"

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#else
#include <time.h>
#endif

namespace {

// Monotonic wall clock, in seconds.
double wallSeconds() {
#ifdef _WIN32
    LARGE_INTEGER freq, now;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&now);
    return (double)now.QuadPart / (double)freq.QuadPart;
#else
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

// CPU time of the whole process over all its threads, in seconds. On Windows clock() measures
// real time, so GetProcessTimes is required; its resolution is about 15.6 ms.
double cpuSeconds() {
#ifdef _WIN32
    FILETIME created, exited, kernel, user;
    if (!GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user)) return 0.0;
    ULARGE_INTEGER k, u;
    k.LowPart = kernel.dwLowDateTime;
    k.HighPart = kernel.dwHighDateTime;
    u.LowPart = user.dwLowDateTime;
    u.HighPart = user.dwHighDateTime;
    return (double)(k.QuadPart + u.QuadPart) * 100e-9;
#else
    timespec ts;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

struct Options {
    int threads = 1;
    bool dumpAll = false;
    bool frames = false;
    const char* statsPath = nullptr;
};

bool parseOptions(int argc, char** argv, Options& o) {
    for (int i = 1; i < argc; i++) {
        const char* a = argv[i];
        if (!strcmp(a, "--threads")) {
            if (++i >= argc) {
                fprintf(stderr, "error: --threads needs a value\n");
                return false;
            }
            char* end;
            errno = 0;
            long n = strtol(argv[i], &end, 10);
            if (errno || end == argv[i] || *end || n < 1 || n > 4096) {
                fprintf(stderr, "error: invalid thread count '%s'\n", argv[i]);
                return false;
            }
            o.threads = (int)n;
        } else if (!strcmp(a, "--dump-all")) {
            o.dumpAll = true;
        } else if (!strcmp(a, "--frames")) {
            o.frames = true;
        } else if (!strcmp(a, "--stats-file")) {
            if (++i >= argc) {
                fprintf(stderr, "error: --stats-file needs a path\n");
                return false;
            }
            o.statsPath = argv[i];
        } else {
            fprintf(stderr, "error: unknown option '%s'\n", a);
            return false;
        }
    }
    if (o.dumpAll && o.frames) {
        fprintf(stderr, "error: --dump-all and --frames both use stdout, choose one\n");
        return false;
    }
    return true;
}

char* appendInt(char* p, int v) {
    char tmp[12];
    int n = 0;
    do {
        tmp[n++] = (char)('0' + v % 10);
        v /= 10;
    } while (v > 0);
    while (n > 0) *p++ = tmp[--n];
    return p;
}

char* appendDashes(char* p, int n) {
    memset(p, '-', (size_t)n);
    return p + n;
}

// Writes the --dump-all, --frames and --stats-file outputs, and accumulates the time they take so
// that it can be taken out of the measured time.
class OutputObserver final : public Observer {
public:
    OutputObserver(const Options& o, FILE* stats) : opt_(o), stats_(stats) {}
    ~OutputObserver() override {
        delete[] lineBuf_;
        delete[] frameBuf_;
    }

    bool active() const { return opt_.dumpAll || opt_.frames || stats_; }
    double wallSpent() const { return wallSpent_; }
    double cpuSpent() const { return cpuSpent_; }

    bool prepare(const World& w) {
        const size_t cols = (size_t)w.cfg.cols;
        if (opt_.dumpAll) {
            // Three grids of at most 11 characters per cell, plus borders and separators.
            lineBuf_ = new (std::nothrow) char[3 * (cols * 11 + 4) + 16];
            if (!lineBuf_) return false;
        }
        if (opt_.frames) {
            frameBuf_ = new (std::nothrow) unsigned char[16 + (size_t)w.cfg.rows * cols];
            if (!frameBuf_) return false;
        }
        return true;
    }

    void onGeneration(int gen, const World& w) override {
        const double wall0 = wallSeconds();
        const double cpu0 = cpuSeconds();
        if (opt_.dumpAll) writeDump(gen, w);
        if (opt_.frames || stats_) {
            int rabbits, foxes, rocks;
            countKinds(w, rabbits, foxes, rocks);
            if (opt_.frames) writeFrame(gen, w, rabbits, foxes, rocks);
            if (stats_) fprintf(stats_, "%d,%d,%d\n", gen, rabbits, foxes);
        }
        wallSpent_ += wallSeconds() - wall0;
        cpuSpent_ += cpuSeconds() - cpu0;
    }

private:
    static void countKinds(const World& w, int& rabbits, int& foxes, int& rocks) {
        rabbits = foxes = rocks = 0;
        const size_t total = (size_t)w.cfg.rows * w.cfg.cols;
        for (size_t i = 0; i < total; i++) {
            const uint8_t k = w.cur[i].kind;
            rabbits += k == RABBIT;
            foxes += k == FOX;
            rocks += k == ROCK;
        }
    }

    static void putInt32LE(unsigned char* p, int32_t v) {
        const uint32_t u = (uint32_t)v;
        p[0] = (unsigned char)(u & 0xFF);
        p[1] = (unsigned char)((u >> 8) & 0xFF);
        p[2] = (unsigned char)((u >> 16) & 0xFF);
        p[3] = (unsigned char)((u >> 24) & 0xFF);
    }

    void writeFrame(int gen, const World& w, int rabbits, int foxes, int rocks) {
        putInt32LE(frameBuf_, gen);
        putInt32LE(frameBuf_ + 4, rabbits);
        putInt32LE(frameBuf_ + 8, foxes);
        putInt32LE(frameBuf_ + 12, rocks);
        const size_t total = (size_t)w.cfg.rows * w.cfg.cols;
        for (size_t i = 0; i < total; i++) frameBuf_[16 + i] = w.cur[i].kind;
        fwrite(frameBuf_, 1, 16 + total, stdout);
        fflush(stdout);  // A live reader must get each frame as soon as it exists.
    }

    void writeBorder(int cols) {
        char* p = lineBuf_;
        p = appendDashes(p, cols + 2);
        memcpy(p, "   ", 3);
        p += 3;
        p = appendDashes(p, cols + 2);
        *p++ = ' ';
        p = appendDashes(p, cols + 2);
        *p++ = '\n';
        fwrite(lineBuf_, 1, (size_t)(p - lineBuf_), stdout);
    }

    // The allgen format. Numbers are printed in full, so a row with an age or hunger of two digits
    // is wider than the others.
    void writeDump(int gen, const World& w) {
        const int cols = w.cfg.cols;
        if (gen > 0) putc('\n', stdout);
        fprintf(stdout, "Generation %d\n", gen);
        writeBorder(cols);
        for (int x = 0; x < w.cfg.rows; x++) {
            const Cell* row = &w.at(w.cur, x, 0);
            char* p = lineBuf_;
            *p++ = '|';
            for (int y = 0; y < cols; y++) {
                const uint8_t k = row[y].kind;
                *p++ = k == ROCK ? '*' : k == RABBIT ? 'R' : k == FOX ? 'F' : ' ';
            }
            memcpy(p, "|   |", 5);
            p += 5;
            for (int y = 0; y < cols; y++) {
                const uint8_t k = row[y].kind;
                if (k == ROCK) *p++ = '*';
                else if (k == EMPTY) *p++ = ' ';
                else p = appendInt(p, row[y].procAge);
            }
            memcpy(p, "| |", 3);
            p += 3;
            for (int y = 0; y < cols; y++) {
                const uint8_t k = row[y].kind;
                if (k == ROCK) *p++ = '*';
                else if (k == EMPTY) *p++ = ' ';
                else if (k == RABBIT) *p++ = 'R';
                else p = appendInt(p, row[y].foodAge);
            }
            *p++ = '|';
            *p++ = '\n';
            fwrite(lineBuf_, 1, (size_t)(p - lineBuf_), stdout);
        }
        writeBorder(cols);
    }

    Options opt_;
    FILE* stats_;
    char* lineBuf_ = nullptr;
    unsigned char* frameBuf_ = nullptr;
    double wallSpent_ = 0.0;
    double cpuSpent_ = 0.0;
};

}  // namespace

int engineMain(int argc, char** argv, Simulator& sim) {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    Options opt;
    if (!parseOptions(argc, argv, opt)) return 2;

    World w;
    char err[160];
    if (!readWorld(stdin, w, err, sizeof err)) {
        fprintf(stderr, "error: %s\n", err);
        return 2;
    }

    FILE* stats = nullptr;
    if (opt.statsPath) {
        stats = fopen(opt.statsPath, "wb");
        if (!stats) {
            fprintf(stderr, "error: cannot open stats file '%s'\n", opt.statsPath);
            return 2;
        }
        fputs("gen,rabbits,foxes\n", stats);
    }

    OutputObserver output(opt, stats);
    if (!output.prepare(w)) {
        fprintf(stderr, "error: cannot allocate output buffers\n");
        if (stats) fclose(stats);
        return 2;
    }
    Observer* obs = output.active() ? &output : nullptr;
    if (obs) obs->onGeneration(0, w);
    const double observerWall0 = output.wallSpent();
    const double observerCpu0 = output.cpuSpent();

    const double wall0 = wallSeconds();
    const double cpu0 = cpuSeconds();
    sim.run(w, opt.threads, obs);
    double wall = wallSeconds() - wall0 - (output.wallSpent() - observerWall0);
    double cpu = cpuSeconds() - cpu0 - (output.cpuSpent() - observerCpu0);
    if (wall < 0.0) wall = 0.0;
    if (cpu < 0.0) cpu = 0.0;

    if (!opt.dumpAll && !opt.frames) writeWorld(stdout, w);

    bool ok = fflush(stdout) == 0 && !ferror(stdout);
    if (stats) {
        ok = !ferror(stats) && ok;
        ok = fclose(stats) == 0 && ok;
    }
    fprintf(stderr, "time wall=%.6f cpu=%.6f threads=%d imbalance=%.3f\n", wall, cpu,
            sim.threadsUsed(opt.threads), sim.imbalance());
    if (!ok) {
        fprintf(stderr, "error: cannot write the output\n");
        return 1;
    }
    return 0;
}
