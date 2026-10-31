// Barrier microbenchmark: cost of empty barriers for OpenMP and Pthreads.
// Build: g++ -O3 -std=gnu++17 -fopenmp -pthread experiments/barrier_bench.cpp -o barrier_bench
// Usage: barrier_bench [barriers=40000] [reps=7]   (prints CSV on stdout)
// Thread creation is outside the timed region; the clock starts after a warm-up barrier.
#include <omp.h>
#include <pthread.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <vector>

using Clock = std::chrono::steady_clock;

static pthread_barrier_t gBarrier;
static int gBarriers;
static double gPthSeconds;

static void* pthWorker(void* arg) {
    bool timer = (arg != nullptr);
    pthread_barrier_wait(&gBarrier);  // warm-up: all threads are running
    Clock::time_point t0;
    if (timer) t0 = Clock::now();
    for (int i = 0; i < gBarriers; i++) pthread_barrier_wait(&gBarrier);
    if (timer) gPthSeconds = std::chrono::duration<double>(Clock::now() - t0).count();
    return nullptr;
}

static double benchPthreads(int threads) {
    pthread_barrier_init(&gBarrier, nullptr, threads);
    std::vector<pthread_t> h(threads);
    for (int t = 1; t < threads; t++) pthread_create(&h[t], nullptr, pthWorker, nullptr);
    pthWorker(&gBarrier);  // the calling thread is thread 0 and keeps the time
    for (int t = 1; t < threads; t++) pthread_join(h[t], nullptr);
    pthread_barrier_destroy(&gBarrier);
    return gPthSeconds;
}

static double benchOpenMP(int threads) {
    double seconds = 0;
#pragma omp parallel num_threads(threads)
    {
#pragma omp barrier
        Clock::time_point t0 = Clock::now();
        for (int i = 0; i < gBarriers; i++) {
#pragma omp barrier
        }
        if (omp_get_thread_num() == 0) seconds = std::chrono::duration<double>(Clock::now() - t0).count();
    }
    return seconds;
}

int main(int argc, char** argv) {
    gBarriers = argc > 1 ? atoi(argv[1]) : 40000;
    int reps = argc > 2 ? atoi(argv[2]) : 7;
    printf("design,threads,rep,barriers,total_s,us_per_barrier\n");
    for (int rep = 1; rep <= reps; rep++) {
        for (int threads : {2, 4, 8, 16}) {
            // alternate which design goes first between repetitions
            for (int k = 0; k < 2; k++) {
                bool pth = ((k + rep) % 2 == 0);
                double s = pth ? benchPthreads(threads) : benchOpenMP(threads);
                printf("%s,%d,%d,%d,%.6f,%.3f\n", pth ? "pth" : "omp", threads, rep, gBarriers, s,
                       s / gBarriers * 1e6);
                fflush(stdout);
            }
        }
    }
    return 0;
}
