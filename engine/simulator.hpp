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
    // Name of the one option with a value that only this simulator takes, or null. The driver parses
    // it and hands the value to setExtraOption, which returns false if the value is not valid.
    virtual const char* extraOption() const { return nullptr; }
    virtual bool setExtraOption(const char*) { return false; }
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

struct Band;

class OmpSimulator final : public Simulator {
public:
    // Row cost is cols + ANIMAL_WEIGHT * animals in the row, recomputed every REBALANCE_EVERY
    // generations. Chosen by measuring input100x100_unbal01 and unbal02, see the report.
    static constexpr int ANIMAL_WEIGHT = 8;
    static constexpr int REBALANCE_EVERY = 50;

    OmpSimulator() = default;
    ~OmpSimulator() override;
    OmpSimulator(const OmpSimulator&) = delete;
    OmpSimulator& operator=(const OmpSimulator&) = delete;

    void run(World& w, int threads, Observer* obs) override;
    // The runtime may give a smaller team than requested, for example under OMP_THREAD_LIMIT.
    int threadsUsed(int requested) const override { return team_ > 0 ? team_ : requested; }
    double imbalance() const override { return imbalance_; }
    const char* extraOption() const override { return "--schedule"; }
    bool setExtraOption(const char* value) override;  // adaptive (the default) or static.

    // The bands in use when the last run ended, threadsUsed() of them.
    const Band* finalBands() const { return bands_; }
    // The thread that owned each row when the last run ended.
    const int* finalRowOwners() const { return rowOwner_; }

private:
    bool adaptive_ = true;
    int team_ = 0;
    double imbalance_ = 1.0;
    Band* bands_ = nullptr;
    int* rowOwner_ = nullptr;
};
