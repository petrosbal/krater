#include "workload_runner.h"

#define VAL_A 1.1
#define VAL_B 2.2

static long N;
static double *restrict A, *restrict B, *restrict C;

static void bench_setup(void) {
    N = krater_param_int("KRATER_SIZE", 256);
    if (N<1) {
        fprintf(stderr, "error: N must be greater than zero\n");
        exit(1);
    }
    A = malloc(N*N*sizeof(double));
    B = malloc(N*N*sizeof(double));
    C = malloc(N*N*sizeof(double));
    if (!A || !B || !C) {
        fprintf(stderr, "error: malloc() failed for N=%ld\n", N);
        exit(1);
    }
    for (int i=0;i<N*N;i++) {
        A[i] = VAL_A; B[i] = VAL_B;
    }
}

static void bench_unit(void) {
    for(int i=0;i<N*N;i++) C[i] = 0.0;
    for (int i = 0; i < N; i++) {
        for (int k = 0; k < N; k++) {
            double r = A[i * N + k];
            for (int j = 0; j < N; j++) {
                C[i * N + j] += r * B[k * N + j];
            }
        }
    }
}

static void bench_report(long units, double elapsed) {
    double expected_value = VAL_A * VAL_B * N;
    double tolerance = 1e-9 *N;
    int valid = 1;

    for (int i = 0; i < N*N; i++) {
        if (fabs(C[i] - expected_value) > tolerance) { // found a mismatch
            fprintf(stderr, "\nERROR\nc[i]: %10.9f\nexp:  %10.9f\ndiff: %10.9f\ntol:  %10.9f\n\n",
                            C[i], expected_value, fabs(C[i] - expected_value), tolerance);
            valid = 0;
            break;
        }
    }

    krater_add_num("throughput_mflops", 2.0 * N * N * N * units / elapsed / 1e6);
    krater_add_bool("valid", valid);
}