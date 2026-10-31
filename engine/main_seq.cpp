// Placeholder sequential entry point: reads the world and writes it back.
#include <cstdio>

#include "io.hpp"

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

int main() {
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    World w;
    char err[160];
    if (!readWorld(stdin, w, err, sizeof err)) {
        fprintf(stderr, "error: %s\n", err);
        return 2;
    }
    writeWorld(stdout, w);
    return 0;
}
