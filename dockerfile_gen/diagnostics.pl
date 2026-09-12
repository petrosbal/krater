%%% diagnostics.pl
%%%
%%% Outside the Dockerfile generator pipeline.
%%% An attempt at explaining why a derivation produced nothing. Every predicate
%%% here runs only after a derivation has already failed, so none of them is on
%%% the path of a successful run.

:- module(diagnostics, [explain/1]).
:- use_module(build_facts).
:- use_module(derivation).

% ==============================================================================
%!  toolchain_requirement(Table, Description).
%       Every table a toolchain must have a row in before its stage can be
%       built.
toolchain_requirement(builder_image,       'base image').
toolchain_requirement(toolchain_binary,    'compiler binary').
toolchain_requirement(optimization_syntax, 'optimization flag syntax').
toolchain_requirement(stage_setup,         'setup list').

% ==============================================================================
%!  problem(Message).
%       Succeeds once for each thing that stops the current facts deriving a
%       Dockerfile, with Message naming what is missing and which target or
%       toolchain it is missing for.
problem(Message):-
    stage_steps(Toolchain, _),
    toolchain_requirement(Table, Description),
    Goal =.. [Table, Toolchain, _],
    \+ call(Goal),
    format(atom(Message), 'toolchain ~w has no ~w: ~w has no row for it',
                          [Toolchain, Description, Table]).

problem(Message):-
    target(Target),
    \+ target_toolchain(Target, _),
    workload_language(Language),
    code_format(Target, CodeFormat),
    format(atom(Message), 'no toolchain compiles ~w to ~w, needed by target ~w',
                          [Language, CodeFormat, Target]).

problem(Message):-
    target(Target),
    target_toolchain(Target, _),
    \+ target_steps(Target, _),
    format(atom(Message),
        'target ~w has no build pipeline',
        [Target]).

problem(Message):-
    target(Target),
    target_steps(Target, _),
    \+ target_base_image(Target, _),
    format(atom(Message), 'target ~w has no base image',
                          [Target]).

problem(Message):-
    duplicate_targets(Target, Other),
    format(atom(Message), 'target ~w and ~w build the same artifact',
                          [Target, Other]).

% ==============================================================================
%!  report_problems.
%       Prints every problem found, one per line. Says so plainly when the
%       derivation failed for a reason no clause here recognises, rather than
%       printing nothing and implying all is well.
report_problems:-
    setof(Message, problem(Message), Messages),
    format(user_error, 'cannot derive a Dockerfile:~n', []),
    forall(member(Message, Messages),
           format(user_error, '  ~w~n', [Message])),
    !.

report_problems:-
    format(user_error,
           'cannot derive a Dockerfile, and no known cause matched.~n', []).

% ==============================================================================
%!  explain(Reason).
%       Prints why the generator refused. rejected_config prints nothing
%       deliberately: config_reader has already named the offending key, and a
%       second line would only restate it.
explain(no_architecture):-
    format(user_error, '--arch is required, for example --arch=x86_64~n', []).

explain(rejected_config).

explain(underivable):-
    report_problems.

