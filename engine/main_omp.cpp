// OpenMP engine executable.
#include "cli.hpp"

int main(int argc, char** argv) {
    OmpSimulator sim;
    return engineMain(argc, argv, sim);
}
