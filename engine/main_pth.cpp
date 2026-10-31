// Pthreads engine executable.
#include "cli.hpp"

int main(int argc, char** argv) {
    PthSimulator sim;
    return engineMain(argc, argv, sim);
}
