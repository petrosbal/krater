%%% build_facts.pl
%%%
%%% Holds every fact the rest of the generator reads. The only module that
%%% asserts, and config_predicate/1 is the only list of what may be asserted.

:- module(build_facts, [ target/1,
                         code_format/2,
                         link_mode/2,
                         aot_compiler/2,
                         workload_language/1,
                         workload_source/1,
                         optimization_level/1,
                         architecture/1,
                         load_build_facts/2]).
:- use_module(library(apply), [maplist/2]).
:- use_module(config_reader).

% ==============================================================================
%!  config_predicate(Predicate).
%       Every predicate whose facts come from build.yaml. One table declares
%       them dynamic, clears them on a reload, and says which facts may be
%       asserted. architecture/1 is absent because it comes from the command
%       line.
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
%       The kind of code a target produces, either native or wasm. Every
%       target has exactly one.
% ==============================================================================
%!  link_mode(Target, LinkMode).
%       How a target links, either dynamic or static. Only native targets
%       declare it.
% ==============================================================================
%!  aot_compiler(Target, Compiler).
%       The compiler that AOT compiles a wasm target after its wasm build.
%       Only wasm targets declare it.
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
%       The CPU architecture the build machine is running. main.pl asserts
%       it from --arch, so config_predicate/1 does not list it.

% ==============================================================================
%!  assert_config_fact(Fact).
%       Asserts one fact the config declared. Fails on a functor the table does
%       not name, so a typo in config_reader cannot create a private
%       predicate that nothing exports.
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
