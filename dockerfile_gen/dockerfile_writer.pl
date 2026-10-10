%%% dockerfile_writer.pl
%%%
%%% Renders the Dockerfile and writes it. The only module that knows
%%% Dockerfile syntax.

:- module(dockerfile_writer, [write_dockerfile/1]).
:- use_module(library(lists), [member/2]).
:- use_module(derivation).
:- use_module(build_facts).

% ==============================================================================
%!  build_directory(Directory).
%       The directory inside the Docker image where the build happens. Every
%       filename the derivation emits is relative to it, so a stage must
%       WORKDIR here before any COPY or RUN.
build_directory('/build').

% ==============================================================================
%!  render_builder_stage_setup(OutStream, SetupStep).
%       Renders one line that prepares a builder stage before it can compile
%       anything. Each kind of setup step becomes a different instruction.
render_builder_stage_setup(OutStream, download(Url, Archive)):-
    format(OutStream, 'ADD ~w ~w~n', [Url, Archive]).

render_builder_stage_setup(OutStream, run(Command)):-
    format(OutStream, 'RUN ~w~n', [Command]).

% ==============================================================================
%!  render_builder_stage_input(OutStream, Input).
%       Renders one line that brings a file the stage needs into the build
%       directory, either from the build context or from an earlier stage.
render_builder_stage_input(OutStream, source(Path, Filename)):-
    format(OutStream, 'COPY ~w ~w~n', [Path, Filename]).

render_builder_stage_input(OutStream, artifact(Toolchain, Filename)):-
    stage_name(builder(Toolchain), Name),
    build_directory(Directory),
    format(OutStream, 'COPY --from=~w ~w/~w .~n', [Name, Directory, Filename]).

% ==============================================================================
%!  render_builder_stage_step(OutStream, Step).
%       Renders one line that runs a step of a builder stage. Every step
%       becomes a RUN, whatever the toolchain.
render_builder_stage_step(OutStream, Step):-
    step_command(Step, Command),
    format(OutStream, 'RUN ~w~n', [Command]).

% ==============================================================================
%!  render_builder_stage(OutStream, Toolchain).
%       Renders one builder stage, from the FROM line through its setup and
%       inputs to one RUN for each step it owns.
render_builder_stage(OutStream, Toolchain):-
    nl(OutStream),
    builder_image(Toolchain, Image),
    stage_name(builder(Toolchain), Name),
    format(OutStream, 'FROM ~w AS ~w~n', [Image, Name]),
    stage_setup(Toolchain, SetupSteps),
    forall(member(SetupStep, SetupSteps),
           render_builder_stage_setup(OutStream, SetupStep)),
    build_directory(Directory),
    format(OutStream, 'WORKDIR ~w~n', [Directory]),
    stage_inputs(Toolchain, Inputs),
    forall(member(Input, Inputs),
           render_builder_stage_input(OutStream, Input)),
    stage_steps(Toolchain, Steps),
    forall(member(Step, Steps),
           render_builder_stage_step(OutStream, Step)).

% ==============================================================================
%!  render_final_image(OutStream, Target).
%       Renders one target's final image. It sits on a base, copies the one
%       artifact from a builder stage, and sets the command that runs it.
render_final_image(OutStream, Target):-
    nl(OutStream),
    target_base_image(Target, BaseImage),
    stage_name(final(Target), StageName),
    format(OutStream, 'FROM ~w AS ~w~n', [BaseImage, StageName]),
    target_last_step(Target, Step),
    step_toolchain(Step, Toolchain),
    stage_name(builder(Toolchain), BuilderStageName),
    build_directory(Directory),
    target_shipped_filename(Target, Filename),
    target_entrypoint(Target, Path),
    format(OutStream, 'COPY --from=~w ~w/~w ~w~n',
       [BuilderStageName, Directory, Filename, Path]),
    format(OutStream, 'ENTRYPOINT ["~w"]~n', [Path]).

% ==============================================================================
%!  render_header(OutStream).
%       Renders the two comments that say not to edit the file by hand.
render_header(OutStream):-
    format(OutStream,
   "# Automatically generated from build.yaml with the power of Prolog.~n", []),
    format(OutStream, "# You probably don't want to edit this file.~n", []).

% ==============================================================================
%!  render_dockerfile(OutStream).
%       Renders the whole Dockerfile to OutStream, starting with the header,
%       then one block per toolchain, then one block per target.
render_dockerfile(OutStream):-
    not(duplicate_targets(_, _)),
    not(stage_name_collision(_)),
    render_header(OutStream),
    stage_order(Toolchains),
    forall(member(Toolchain, Toolchains),
           render_builder_stage(OutStream, Toolchain)),
    forall(target(Target),
           render_final_image(OutStream, Target)).

% ==============================================================================
%!  write_dockerfile(Path).
%       Writes the Dockerfile to Path. The whole text is rendered before the
%       file is opened, so a derivation that fails leaves Path untouched
%       rather than truncated.
write_dockerfile(Path):-
    with_output_to(string(Text), render_dockerfile(current_output)),
    setup_call_cleanup(
        open(Path, write, OutStream),
        write(OutStream, Text),
        close(OutStream)).
