%%% main.pl
%%%
%%% Reads the command line options and writes both files, or explains the
%%% refusal and exits non-zero. The only module that halts.

:- use_module(library(main), [argv_options/3, main/0]).
:- use_module(library(option), [option/2]).
:- use_module(build_facts).
:- use_module(dockerfile_writer).
:- use_module(environments_writer).
:- use_module(diagnostics).

:- initialization(main, main).

% ==============================================================================
%!  opt_type(Name, Fact, Type).
%       The type of each command line option. Fact is the term argv_options/3
%       returns, which is also what opt_help/2 and opt_meta/2 are keyed on.
opt_type(arch, architecture, atom).

% ==============================================================================
%!  opt_help(Fact, Help).
%       The description --help prints for each command line option.
opt_help(architecture, "Target architecture, e.g. x86_64 or aarch64").

% ==============================================================================
%!  opt_meta(Fact, Placeholder).
%       The placeholder that --help prints for each command line option.
opt_meta(architecture, "ARCH").

% ==============================================================================
%!  or_refuse(Goal, Reason).
%       Runs Goal, and throws refused(Reason) when it has no solution. Failure
%       carries no reason of its own, so without the throw main/1 could only
%       report that something went wrong.
or_refuse(Goal, _):-
    call(Goal), !.

or_refuse(_, Reason):-
    throw(refused(Reason)).

% ==============================================================================
%!  generate(Argv).
%       Reads the command line args, puts the facts in place, and writes the
%       two files. Throws refused/1 at each point that can have no answer.
generate(Argv):-
    argv_options(Argv, Positional, Options),
    or_refuse(Positional == [], unexpected_arguments(Positional)),
    or_refuse(option(architecture(Architecture), Options), no_architecture),
    or_refuse(load_build_facts('build.yaml', Architecture), rejected_config),
    or_refuse(write_dockerfile(
        'dockerfile_gen/generated/Dockerfile'), underivable),
    or_refuse(write_environments(
        'dockerfile_gen/generated/benchmark_environments.yaml'), underivable).

% ==============================================================================
%!  main(Argv).
%       Generates both files, or explains the refusal and exits non-zero. The
%       only predicate that calls halt/1.
main(Argv):-
    catch(generate(Argv), refused(Reason),
          ( explain(Reason), halt(1) )).

