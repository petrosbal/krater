#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <math.h>

#define VAL_A 1.1
#define VAL_B 2.2

void matrix_mult(double *A, double *B, double *C, int N) {
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

int valid_results(double *C, int N) {
    double expected_value = VAL_A * VAL_B * N;
    double tolerance = 1e-9 *N;

    for (int i = 0; i < N*N; i++) {
        if (fabs(C[i] - expected_value) > tolerance) { // found a mismatch
            printf("\nERROR\nc[i]: %10.9f\nexp:  %10.9f\ndiff: %10.9f\ntol:  %10.9f\n\n",
                                C[i], expected_value, fabs(C[i] - expected_value), tolerance);
            return 0;
        }
    }
    return 1;  // all elements are correct
}


int main(int argc, char *argv[]) {
    if (argc < 4) {
        printf("\nUsage:\n%s <w|nw> <matrix_size> <duration_sec>\n\n", argv[0]);
        printf("or, if you have the Makefile:\n");
        printf("make run <w|nw> <matrix_size> <duration_sec>\n\n");
        return 1;
    }

    int do_warmup = (argv[1][0] == 'w');
    int N = atoi(argv[2]);
    double duration = atof(argv[3]);
    if (N <= 0 || duration <= 0) return 1;

    double *A = malloc(N*N*sizeof(double));
    double *B = malloc(N*N*sizeof(double));
    double *C = malloc(N*N*sizeof(double));
    if (!A || !B || !C) return 1;

    for (int i=0;i<N*N;i++) {
        A[i] = VAL_A; B[i] = VAL_B;
    }

    // optional warmup (takes at least 5 secs)
    if (do_warmup) {
        struct timespec w_start, w_now;
        timespec_get(&w_start, TIME_UTC);
        double w_elapsed = 0.0;
        printf("\rWarming up... "); fflush(stdout);
        while (w_elapsed < 5.0) {
            matrix_mult(A,B,C,N);
            timespec_get(&w_now, TIME_UTC);
            w_elapsed = (w_now.tv_sec - w_start.tv_sec) + (w_now.tv_nsec - w_start.tv_nsec)/1e9;
        }
    }

    // actual benchmark
    printf("BENCH_START\n"); fflush(stdout);
    struct timespec t_start, t_now;
    timespec_get(&t_start, TIME_UTC);
    double elapsed = 0.0;
    int iterations = 0;

    while (elapsed < duration) {
        matrix_mult(A,B,C,N);
        iterations++;
        timespec_get(&t_now, TIME_UTC);
        elapsed = (t_now.tv_sec - t_start.tv_sec) + (t_now.tv_nsec - t_start.tv_nsec)/1e9;
    }
    printf("BENCH_END\n"); fflush(stdout);

    double mflops = 2.0 * N * N * N * iterations / elapsed / 1e6; // 2*N^3 flops per matrix multiplication

    printf("\niterations: %d\nelapsed time: %.6f s\nthroughput: %.2f MFLOPS\ncalculation check: %s\n\n",
        iterations,
        elapsed,
        mflops,
        valid_results(C, N) ? "PASSED" : "FAILED");

    free(A); free(B); free(C);
}
