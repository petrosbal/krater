#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# main.pl is skipped because loading it runs the generator
check_modules_load_cleanly() {
    local goals=()
    for module in dice/*.pl; do
        if [ "$module" != dice/main.pl ]; then
            goals+=(-g "use_module('$module')")
        fi
    done
    swipl --on-warning=status "${goals[@]}" -g list_undefined -t halt
}

imported_libraries() {
    grep --only-matching --no-filename --extended-regexp \
        "library\([a-z_]+\)" dice/*.pl |
        sort --unique | paste --serial --delimiters=,
}

# SWI's own libraries need autoload, so they are resolved before it goes off.
check_generator_runs_without_autoload() {
    swipl --on-warning=status \
        -g "load_files([$(imported_libraries)], [imports([])])" \
        -g "autoload_all" \
        -g "set_prolog_flag(autoload, false)" \
        -g "consult('dice/main.pl')" \
        -- --arch=x86_64
}

check_generated_files_are_current() {
    git diff --exit-code dice/generated/
}

check_modules_load_cleanly
check_generator_runs_without_autoload
check_generated_files_are_current
