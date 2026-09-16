%%% runtime_compatibility.pl
%%%
%%% Pairs each target with the runtime classes it may execute under, and names
%%% the image it runs in. A pairing with no clause here can't be written, so
%%% an invalid environment never reaches the harness.

:- module(runtime_compatibility, [environment/2]).
:- use_module(build_facts).

% ==============================================================================
%!  wasm_shim(Runtime).
%       The runtime classes that are runwasi shims, which means they can execute
%       a plain Wasm module.
wasm_shim(wasmtime).
wasm_shim(wasmedge).
wasm_shim(wasmer).

% ==============================================================================
%!  aot_runtime(Compiler, RuntimeClass).
%       The runtime class that can execute what an AOT compiler produces.
%       Both are called wasmedge today, though nothing says a compiler has
%       to target a runtime of the same name.
aot_runtime(wasmedge, wasmedge).

% ==============================================================================
%!  runs_under(Target, RuntimeClass).
%       Succeeds when the target may be benchmarked under the given runtime
%       class. Fails on a pairing that must not run, like Wasmtime on a
%       WasmEdge AOT module, which would JIT the bytecode and still be
%       recorded as AOT.
runs_under(Target, default):-
    code_format(Target, native).

runs_under(Target, Runtime):-
    code_format(Target, wasm),
    aot_compiler(Target, Compiler),
    aot_runtime(Compiler, Runtime).

runs_under(Target, Runtime):-
    code_format(Target, wasm),
    not(aot_compiler(Target, _)),
    wasm_shim(Runtime).

% ==============================================================================
%!  target_image_name(Target, ImageName).
%       Succeeds when ImageName is the image the target runs in.
target_image_name(Target, ImageName):-
    atomic_list_concat([krater, ':', Target], ImageName).

% ==============================================================================
%!  environment(ImageName, RuntimeClass).
%       Succeeds when the image may run under the runtime class. One answer
%       for each environment the harness can measure.
environment(ImageName, RuntimeClass):-
    target(Target),
    runs_under(Target, RuntimeClass),
    target_image_name(Target, ImageName).
