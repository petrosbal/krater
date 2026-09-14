%%% main.pl
%%%
%%% The entry point of the Dockerfile generator pipeline.

:- use_module(library(main)).
:- use_module(library(option)).
:- use_module(build_facts).
:- use_module(dockerfile_writer).
:- use_module(diagnostics).

:- initialization(main, main).

% ==============================================================================
%!  opt_type(Name, Fact, Type).
%       The type of each command line option. The first is the option name, the
%       second is the option term returned, and the third is the term type.
opt_type(arch, architecture, atom).
opt_type(config, config, atom).
opt_type(output, output, atom).

% ==============================================================================
%!  or_refuse(Goal, Reason).
%       Runs Goal, and throws refused(Reason) when it has no solution. The one
%       place a step with no answer becomes something main/1 can act on.
or_refuse(Goal, _):-
    call(Goal),
    !.

or_refuse(_, Reason):-
    throw(refused(Reason)).

% ==============================================================================
%!  generate(Argv).
%       Reads the command line args, puts the facts in place, and writes the
%       Dockerfile. Throws refused/1 at each point that can have no answer.
generate(Argv):-
    argv_options(Argv, Positional, Options),
    or_refuse(Positional == [], unexpected_arguments(Positional)),
    or_refuse(option(architecture(Architecture), Options), no_architecture),
    option(config(ConfigPath), Options, 'build.yaml'),
    option(output(OutputPath), Options, 'Dockerfile.gen'),
    or_refuse(load_build_facts(ConfigPath, Architecture), rejected_config),
    or_refuse(write_dockerfile(OutputPath), underivable).

% ==============================================================================
%!  main(Argv).
%       Generates the Dockerfile, or explains the refusal and exits non-zero.
%       The only predicate in the rule base that ends the process.
main(Argv):-
    catch(generate(Argv), refused(Reason),
          ( explain(Reason), halt(1) )).

