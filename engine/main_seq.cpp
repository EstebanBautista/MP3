// Sequential engine executable.
#include "cli.hpp"

int main(int argc, char** argv) {
    SeqSimulator sim;
    return engineMain(argc, argv, sim);
}
