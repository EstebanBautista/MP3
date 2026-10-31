// Command line driver shared by all engine executables.
#pragma once
#include "simulator.hpp"

// Options: --threads N, --dump-all, --frames, --stats-file PATH, and the sim.extraOption() if any.
// Reads the world from stdin and returns the process exit code: 0 on success, 2 on bad usage or
// bad input, 1 if the output could not be written or another resource failure happened (for
// example running out of memory).
int engineMain(int argc, char** argv, Simulator& sim);
