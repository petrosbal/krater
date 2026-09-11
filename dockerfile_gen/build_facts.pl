%%% build_facts.pl
%%%
%%% Part #2 of the Dockerfile generator pipeline.
%%% Receives the facts from config_reader and asserts them.

:- module(build_facts, [ target/1,
                         code_format/2,
                         link_mode/2,
                         aot_compiler/2,
                         workload_language/1,
                         workload_source/1,
                         optimization_level/1,
                         architecture/1,
                         load_build_facts/2]).
:- use_module(config_reader).

% ==============================================================================
%!  config_predicate(Predicate).
%       Every predicate whose facts come from build.yaml. One table declares
%       them dynamic, clears them on a reload, and says which facts may be
%       asserted at all. architecture/1 is absent on purpose: it comes from the
%       command line, not the config.
config_predicate(target(_)).
config_predicate(code_format(_,_)).
config_predicate(link_mode(_,_)).
config_predicate(aot_compiler(_,_)).
config_predicate(workload_language(_)).
config_predicate(workload_source(_)).
config_predicate(optimization_level(_)).

:- forall(config_predicate(Predicate),
        ( functor(Predicate, Functor, Arity), dynamic(Functor/Arity) )).

% ==============================================================================
%!  target(Name).
%       One of the things this workload can be built as. Each one becomes a
%       Docker image.
% ==============================================================================
%!  code_format(Target, CodeFormat).
%       The kind of code a target produces: native or wasm. Every target has
%       exactly one.
% ==============================================================================
%!  link_mode(Target, LinkMode).
%       Succeeds when the target links the given way (dynamic or static).
% ==============================================================================
%!  aot_compiler(Target, Compiler).
%       Succeeds when this wasm target gets an extra AOT compile step using the
%       given compiler after the wasm build.
% ==============================================================================
%!  workload_language(Language).
%       The language the workload is written in.
% ==============================================================================
%!  workload_source(Source).
%       The file name of the workload source code.
% ==============================================================================
%!  optimization_level(Level).
%       The optimization level applied to every build.

% ==============================================================================
:- dynamic(architecture/1).
%!  architecture(Name).
%       The CPU architecture the build machine is running.
%       Does not come from build.yaml, but from main.pl as a cmdline arg.

% ==============================================================================
%!  assert_config_fact(Fact).
%       Asserts one fact the config declared. Fails on a functor the table does
%       not name, so a typo in config_reader cannot quietly create a private
%       predicate nothing exports.
assert_config_fact(Fact):-
    config_predicate(Fact),
    assertz(Fact).

% ==============================================================================
%!  load_build_facts(ConfigPath, Architecture).
%       Replaces the whole fact base. Reads (and validates) before retracting
%       anything, so that a rejected config leaves the previous facts intact.
load_build_facts(ConfigPath, Architecture):-
    read_config(ConfigPath, Facts),
    forall(config_predicate(Predicate), retractall(Predicate)),
    maplist(assert_config_fact, Facts),
    retractall(architecture(_)),
    assertz(architecture(Architecture)).
