// Command line driver shared by all engine executables.
#pragma once
#include "simulator.hpp"

// Options: --threads N, --dump-all, --frames, --stats-file PATH, and the sim.extraOption() if any.
// Reads the world from stdin and returns the process exit code: 0 on success, 2 on bad usage or
// bad input, 1 if the output could not be written.
int engineMain(int argc, char** argv, Simulator& sim);
