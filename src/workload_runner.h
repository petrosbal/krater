/* 
    This is KRATER's runner for C workloads, included by the workload's .c file.
    The workload defines only three functions and no main().
    Timing, markers and output all belong to the runner, and a workload never
    prints its own results.
*/

#ifndef KRATER_WORKLOAD_RUNNER_H
#define KRATER_WORKLOAD_RUNNER_H
#include <time.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <ctype.h>
#include <string.h>
#include <unistd.h>

//====== WORKLOAD-DEFINED FUNCTIONS (WRITE THESE IN YOUR .C FILE) ==============

// called once, before warmup and before timing starts
// useful for memory allocation and krater_param_* value reads.
static void bench_setup(void);

// one unit of work. the thing being measured. called repeatedly at least once.
// should do the same amount of work every call.
static void bench_unit(void);

// called once after timing ends, for validity checks, throughput calculation
// or additional metrics with krater_add_*
static void bench_report(long units, double elapsed);

//=============================== THE API ======================================

// reads the 'name' env var as a whole number. if unset or empty, returns fallback. exits 1 on bad input
static inline long krater_param_int(const char *name, long fallback);
// same as above, but for decimals. accepts scientific notation
static inline double krater_param_double(const char *name, double fallback);

// call only from bench_report():
// records a numeric metric that appears in results under 'name'. nan or inf are reported as null
static inline void krater_add_num(const char *name, double value);
// records a boolean metric. any non-zero value means true.
static inline void krater_add_bool(const char *name, int value);

//========================== RUNNER INTERNALS ==================================

typedef enum { RUNNER_NUM, RUNNER_BOOL } runner_kind;

typedef struct {
    const char *name;
    runner_kind kind;
    double value;
} runner_metric;

#define RUNNER_MAX_METRICS 16
// metrics table
static runner_metric runner_metrics[RUNNER_MAX_METRICS];
static int runner_metric_count = 0;

static void runner_check_metric_name(const char *name) {
    if (!isalpha((unsigned char)name[0])) {
        fprintf(stderr, "krater: \"%s\" metric's name must start with a letter\n", name);
        exit(1);
    }
    for (int i = 1; name[i] != '\0'; i++) {
        unsigned char c = (unsigned char)name[i];
        if (!isalnum(c) && c != '_') {
            fprintf(stderr, "krater: \"%s\" metric's name must contain only letters, numbers or underscores\n", name);
            exit(1);
        }
    }
    if (strcmp("units", name) == 0 || strcmp("elapsed_seconds", name) == 0) {
        fprintf(stderr, "krater: \"%s\" metric already exists by default\n", name);
        exit(1);
    }
    for (int i = 0; i < runner_metric_count; i++) {
        if (strcmp(runner_metrics[i].name, name) == 0) {
            fprintf(stderr, "krater: \"%s\" metric already exists\n", name);
            exit(1);
        }
    }
}

static inline long krater_param_int(const char *name, long fallback) {
    const char *text = getenv(name);
    if (text == NULL || text[0] == '\0') return fallback;
    char* end;
    long value = strtol(text, &end, 10);
    if (end == text || *end != '\0') {
        fprintf(stderr, "krater: %s=\"%s\" is not an integer\n", name, text);
        exit(1);
    }
    return value;
}

static inline double krater_param_double(const char *name, double fallback) {
    const char *text = getenv(name);
    if (text == NULL || text[0] == '\0') return fallback;
    char* end;
    double value = strtod(text, &end);
    if (end == text || *end != '\0') {
        fprintf(stderr, "krater: %s=\"%s\" is not a number\n", name, text);
        exit(1);
    }
    return value;
}

// calls bench_unit() iteratively for the specified duration
// returns unit count and writes measured time to *elapsed parameter.
static long runner_run_for(double duration, double *elapsed) {
    long units = 0;
    struct timespec start, now;
    timespec_get(&start, TIME_UTC);
    double temp;
    do {
        bench_unit();
        units++;
        timespec_get(&now, TIME_UTC);
        temp = (double)(now.tv_sec - start.tv_sec) + (double)(now.tv_nsec - start.tv_nsec) / 1e9;
    } while (temp < duration);
    *elapsed = temp;
    return units;
}

// adds a metric to the metrics table
static void runner_add_metric(const char *name, runner_kind kind, double value) {
    runner_check_metric_name(name);
    if (runner_metric_count == RUNNER_MAX_METRICS) {
        fprintf(stderr, "krater: metric table full (%d), "
                        "cannot add \"%s\"\n", RUNNER_MAX_METRICS, name);
        exit(1);
    }
    runner_metrics[runner_metric_count++] = (runner_metric){ name, kind, value };
}

static inline void krater_add_num(const char *name, double value) {
    runner_add_metric(name, RUNNER_NUM, value);
}

static inline void krater_add_bool(const char *name, int value) {
    runner_add_metric(name, RUNNER_BOOL, value ? 1.0 : 0.0);
}

static void runner_print_result(long units, double elapsed) {
    printf("BENCH_RESULT {\"units\": %ld, \"elapsed_seconds\": %.17g", units, elapsed);
    for (int i = 0; i < runner_metric_count; i++) {
        const runner_metric m = runner_metrics[i];
        printf(",\"%s\":", m.name);
        if (m.kind == RUNNER_BOOL) printf("%s", m.value == 1.0 ? "true" : "false");
        else if (m.kind == RUNNER_NUM) {
            if (isfinite(m.value)) printf("%.17g", m.value);
            else printf("null");
        }
    }
    printf("}\n");
    fflush(stdout);
}

int main(void) {
    printf("MAIN_START\n"); fflush(stdout);

    // Kubernetes takes some time to report when a container starts (~1 s), so the harness
    // can't start sampling until that. the cgroup path discovery isnt instant either (~200ms).
    sleep(2); // measured worst case was 1.4 seconds

    double duration = krater_param_double("KRATER_DURATION", 30.0);
    double warmup_duration = krater_param_double("KRATER_WARMUP", 0.0);
    bench_setup();

    if (warmup_duration > 0) {
        double throwaway;
        runner_run_for(warmup_duration, &throwaway);
    }

    printf("BENCH_START\n"); fflush(stdout);
    double elapsed;
    long units = runner_run_for(duration, &elapsed);
    printf("BENCH_END\n"); fflush(stdout);

    bench_report(units, elapsed);
    runner_print_result(units, elapsed);

    // similarly, i force the cgroup to stay 2s more so that
    // at least one sample after BENCH_END is recorded.
    sleep(2);
}
#endif