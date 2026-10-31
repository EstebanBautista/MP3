// Interfaces between the simulation algorithms and the command line driver.
#pragma once
#include "world.hpp"

// Receives the world after each generation. Implementations may do I/O.
class Observer {
public:
    virtual ~Observer() = default;
    // Called with gen=0 by engineMain, and by the simulator with gen=g+1 once generation g is
    // complete, from one thread only and while no other thread touches the world. The state to
    // read is w.cur.
    virtual void onGeneration(int gen, const World& w) = 0;
};

class Simulator {
public:
    virtual ~Simulator() = default;
    // Runs w.cfg.nGen generations, leaving the final state in w.cur. obs may be null.
    virtual void run(World& w, int threads, Observer* obs) = 0;
    // Threads really used for a request of `requested` threads.
    virtual int threadsUsed(int requested) const { return requested; }
    // Load imbalance of the last run: maximum worker busy time divided by the mean.
    virtual double imbalance() const { return 1.0; }
};

class SeqSimulator final : public Simulator {
public:
    void run(World& w, int threads, Observer* obs) override;
    int threadsUsed(int) const override { return 1; }
};

class PthSimulator final : public Simulator {
public:
    void run(World& w, int threads, Observer* obs) override;
    double imbalance() const override { return imbalance_; }

private:
    double imbalance_ = 1.0;
};
