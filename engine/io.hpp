// Reading and writing the assignment text format.
#pragma once
#include <cstddef>
#include <cstdio>

#include "world.hpp"

// Parses the world from f. On failure returns false and writes a message to err.
bool readWorld(FILE* f, World& w, char* err, size_t errLen);
// Writes the world with N_GEN printed as 0, objects in row then column order.
void writeWorld(FILE* f, const World& w);
