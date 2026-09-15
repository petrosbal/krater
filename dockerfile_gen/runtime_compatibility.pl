%%% runtime_compatibility.pl
%%%
%%% Outside the Dockerfile generator pipeline.
%%% Which targets may execute under which runtime classes. A pairing with no
%%% clause here is one that must not reach the harness. Nothing here generates
%%% anything.

:- module(runtime_compatibility, [environment/2]).
:- use_module(build_facts).

% ==============================================================================
%!  wasm_shim(Runtime).
%       Succeeds when the runtime class is a runwasi shim, meaning it can
%       execute a plain wasm module.
wasm_shim(wasmtime).
wasm_shim(wasmedge).
wasm_shim(wasmer).

% ==============================================================================
%!  aot_runtime(Compiler, RuntimeClass).
%       The runtime class that can execute what an AOT compiler produces.
%       Usually the same name, but the two are different concepts.
aot_runtime(wasmedge, wasmedge).

% ==============================================================================
%!  runs_under(Target, RuntimeClass).
%       Succeeds when the target may be benchmarked under the given runtime
%       class. Fails on a pairing that must not run, like Wasmtime running a
%       WasmEdge AOT module.
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
%       Succeeds when ImageName is the name of the image the target runs in.
target_image_name(Target, ImageName):-
    atomic_list_concat([krater, ':', Target], ImageName).

% ==============================================================================
%!  environment(ImageName, RuntimeClass).
%       Succeeds when ImageName is the name of the image the target runs in, and
%       RuntimeClass is the runtime class it may execute under.
environment(ImageName, RuntimeClass):-
    target(Target),
    runs_under(Target, RuntimeClass),
    target_image_name(Target, ImageName).
