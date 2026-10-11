%%% environments_writer.pl
%%%
%%% Renders benchmark_environments.yaml and writes it. The only module that
%%% knows that file's syntax.

:- module(environments_writer, [write_environments/1]).
:- use_module(runtime_compatibility).

% ==============================================================================
%!  render_header(OutStream).
%       Renders the two comments that say not to edit the file by hand.
render_header(OutStream):-
    format(OutStream,
   "# Automatically generated from build.yaml with the power of Prolog.~n", []),
    format(OutStream, "# You probably don't want to edit this file.~n", []).

% ==============================================================================
%!  render_environment(OutStream, Target, ImageName, RuntimeClass).
%       Renders a blank line, then the environment's target, image and runtime
%       class.
render_environment(OutStream, Target, ImageName, RuntimeClass):-
    nl(OutStream),
    format(OutStream, '  - target: ~w~n', [Target]),
    format(OutStream, '    image: ~w~n', [ImageName]),
    format(OutStream, '    runtime_class: ~w~n', [RuntimeClass]).

% ==============================================================================
%!  render_environments(OutStream).
%       Renders the whole file to OutStream.
render_environments(OutStream):-
    render_header(OutStream),
    nl(OutStream),
    write(OutStream, 'environments:'),
    forall(environment(Target, ImageName, RuntimeClass),
           render_environment(OutStream, Target, ImageName, RuntimeClass)).

% ==============================================================================
%!  write_environments(Path).
%       Writes the environments to Path. The whole text is rendered before the
%       file is opened, so a failure leaves Path untouched.
write_environments(Path):-
    with_output_to(string(Text), render_environments(current_output)),
    setup_call_cleanup(
        open(Path, write, OutStream),
        write(OutStream, Text),
        close(OutStream)).
