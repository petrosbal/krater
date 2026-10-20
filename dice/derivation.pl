%%% derivation.pl
%%%
%%% Derives the build graph of toolchains, steps, stages, order, filenames
%%% and commands. Knows no output syntax, so nothing here can render a line.

:- module(derivation, [ stage_steps/2,
                        stage_name/2,
                        builder_image/2,
                        step_toolchain/2,
                        step_command/2,
                        target_last_step/2,
                        target_shipped_filename/2,
                        target_entrypoint/2,
                        target_base_image/2,
                        stage_setup/2,
                        stage_inputs/2,
                        stage_order/1,
                        target_toolchain/2,
                        target_steps/2,
                        toolchain_binary/2,
                        optimization_syntax/2,
                        toolchain_asset/3,
                        duplicate_targets/2,
                        stage_name_collision/1,
                        workload_basename/1 ]).
:- use_module(library(lists), [append/2, member/2, last/2]).
:- use_module(library(ugraphs), [top_sort/2, vertices_edges_to_ugraph/3]).
:- use_module(build_facts).

% ==============================================================================
%!  language_toolchain(Language, CodeFormat, Toolchain).
%       Which toolchain compiles a given language into a given code format.
language_toolchain(c,    native, gcc).
language_toolchain(c,    wasm,   wasi_sdk).
language_toolchain(rust, native, rustc).
language_toolchain(rust, wasm,   rustc_wasm).

% ==============================================================================
%!  target_toolchain(Target, Toolchain).
%       Succeeds when Toolchain is what compiles the target.
target_toolchain(Target, Toolchain):-
    workload_language(Language),
    code_format(Target, CodeFormat),
    language_toolchain(Language, CodeFormat, Toolchain).

% ==============================================================================
%!  toolchain_supports(Toolchain, Attribute, Value).
%       Every target attribute value a toolchain accepts. An allowlist, so a
%       pairing with no row can't be produced by this toolchain. A new AOT
%       compiler or link mode is one row.
toolchain_supports(gcc, link_mode, 'dynamic').
toolchain_supports(gcc, link_mode, static).
toolchain_supports(wasi_sdk, aot_compiler, wasmedge).
toolchain_supports(rustc, link_mode, 'dynamic').
toolchain_supports(rustc, link_mode, static).

% ==============================================================================
%!  target_attributes_supported(Target).
%       Succeeds when every attribute the target declares is supported by its
%       toolchain. The attributes checked are those toolchain_supports/3 has
%       rows for.
target_attributes_supported(Target):-
    target_toolchain(Target, Toolchain),
    forall(( toolchain_supports(_, Attribute, _),
             call(Attribute, Target, Value) ),
           toolchain_supports(Toolchain, Attribute, Value)).

% ==============================================================================
%!  target_modifier(Target, Modifier).
%       Succeeds once for each thing that changes how the target is compiled
%       (other than the optimization level). Clause order fixes the order of
%       the collected list.
target_modifier(Target, static):-
    link_mode(Target, static).

% ==============================================================================
%!  target_compile_step(Target, Step).
%       Succeeds when Step describes how the target is compiled from its
%       source. Two targets compiled the same way get the same term, so the
%       stage runs the command once.
target_compile_step(Target, compile(Toolchain, CodeFormat, Modifiers)):-
    target_attributes_supported(Target),
    code_format(Target, CodeFormat),
    target_toolchain(Target, Toolchain),
    findall(Modifier, target_modifier(Target, Modifier), Modifiers).

% ==============================================================================
%!  target_steps(Target, Steps).
%       Succeeds when Steps is the target's build pipeline in run order. A
%       compile step, then for an AOT target a second step after it. The AOT
%       step carries its input step whole, so step_input/2 can derive the
%       COPY between stages.
target_steps(Target, [Step]):-
    target_compile_step(Target, Step),
    not(aot_compiler(Target, _)).

target_steps(Target, [Step, aot(Compiler, Step)]):-
    target_compile_step(Target, Step),
    aot_compiler(Target, Compiler).

% ==============================================================================
%!  target_last_step(Target, Step).
%       Succeeds when Step is the last step of the target's build pipeline.
target_last_step(Target, Step):-
    target_steps(Target, Steps),
    last(Steps, Step).

% ==============================================================================
%!  duplicate_targets(Target, Other).
%       Succeeds when two differently named targets end in the same build step.
%       They would ship one artifact under two different names, which is
%       probably not what the user intended.
duplicate_targets(Target, Other):-
    target_last_step(Target, Step),
    target_last_step(Other, Step),
    Target @< Other.

% ==============================================================================
%!  step_toolchain(Step, Toolchain).
%       Succeeds when Toolchain is the tool that runs the step. Steps that
%       share a toolchain share one builder stage.
step_toolchain(compile(Toolchain, _, _), Toolchain).
step_toolchain(aot(Toolchain, _), Toolchain).

% ==============================================================================
%!  stage_steps(Toolchain, Steps).
%       Succeeds when Steps is every step the stage runs, in the order it runs
%       them. One answer per builder stage. A step reached by two targets
%       appears once.
stage_steps(Toolchain, Steps):-
    setof(Step,
            Target^TargetSteps^( target_steps(Target, TargetSteps),
                                 member(Step, TargetSteps),
                                 step_toolchain(Step, Toolchain) ),
          Steps).

% ==============================================================================
%!  stage_name(Stage, Name).
%       Succeeds when Name is what a stage is called in the Dockerfile. A
%       builder stage is named after its toolchain, so a new toolchain needs no
%       new fact. A final stage is named after its target, because that name is
%       also what docker build --target takes.
stage_name(builder(Toolchain), Name):-
    atomic_list_concat(['builder_', Toolchain], Name).

stage_name(final(Target), Target).

% ==============================================================================
%!  stage_name_collision(Name).
%       Succeeds when a target is named like a builder stage that exists. Only
%       final against builder names can clash, because builder names come from
%       distinct toolchains, and target names are already distinct.
stage_name_collision(Name):-
    target(Target),
    stage_steps(Toolchain, _),
    stage_name(final(Target), Name),
    stage_name(builder(Toolchain), Name).

% ==============================================================================
%!  toolchain_release(Toolchain, Version).
%       The release each toolchain installs. Better pinned than free.
toolchain_release(wasmedge, '0.14.1').

% ==============================================================================
%!  toolchain_asset(Toolchain, Architecture, Asset).
%       Which release asset carries a toolchain's binaries on each architecture.
%       WasmEdge's debian11 static assets ship only a library, so they cannot be
%       used. An architecture with no row here has no build.
toolchain_asset(wasmedge, x86_64,  'ubuntu20.04_x86_64').
toolchain_asset(wasmedge, aarch64, 'ubuntu20.04_aarch64').

% ==============================================================================
%!  toolchain_url(Toolchain, Url).
%       Succeeds when Url is where the toolchain's release archive is
%       downloaded from, for the architecture in architecture/1. One clause per
%       toolchain, because each project spells its release URL differently.
toolchain_url(wasmedge, Url):-
    toolchain_release(wasmedge, Version),
    architecture(Architecture),
    toolchain_asset(wasmedge, Architecture, Asset),
    atomic_list_concat(
        [ 'https://github.com/WasmEdge/WasmEdge/releases/download/',
        Version, '/WasmEdge-', Version, '-', Asset, '.tar.gz' ], Url).

% ==============================================================================
%!  toolchain_archive(Toolchain, Path).
%       Where a builder stage puts a downloaded release archive before
%       unpacking it.
toolchain_archive(wasmedge, '/tmp/wasmedge.tar.gz').

% ==============================================================================
%!  stage_setup(Toolchain, SetupSteps).
%       Succeeds once per builder stage with every step it must run before its
%       own steps, in order. A stage whose base image already carries its
%       toolchain has an empty list. A stage that needs setup it cannot derive
%       has no answer, so a half-built stage never reaches the Dockerfile.
stage_setup(gcc, []).
stage_setup(rustc, []).
stage_setup(rustc_wasm, [run('rustup target add wasm32-wasip1')]).
stage_setup(wasi_sdk, []).

stage_setup(wasmedge, [download(Url, Archive), run(ExtractCommand)]):-
    toolchain_url(wasmedge, Url),
    toolchain_archive(wasmedge, Archive),
    atomic_list_concat(
        ['tar -xzf', Archive, '-C /usr/local --strip-components=1'],
        ' ', ExtractCommand).

% ==============================================================================
%!  builder_image(Toolchain, BaseImage).
%       What each builder stage runs on.
builder_image(gcc, 'gcc:14-trixie').
builder_image(rustc, 'rust:1-slim-trixie').
builder_image(rustc_wasm, 'rust:1-slim-trixie').
builder_image(wasi_sdk, 'ghcr.io/webassembly/wasi-sdk:wasi-sdk-32').
builder_image(wasmedge, 'debian:trixie-slim').

% ==============================================================================
%!  step_code_format(Step, CodeFormat).
%       Succeeds when CodeFormat is the kind of code the step writes out. An AOT
%       step keeps the format of the step it reads, because it only adds a
%       native section to the module.
step_code_format(compile(_, CodeFormat, _), CodeFormat).
step_code_format(aot(_, Step), CodeFormat):-
    step_code_format(Step, CodeFormat).

% ==============================================================================
%!  artifact_extension(CodeFormat, Extension).
%       The filename extension for a code format's artifacts.
artifact_extension(wasm,   '.wasm').

% ==============================================================================
%!  workload_basename(Basename).
%       Succeeds when Basename is the source filename with its directory and
%       extension removed. Every artifact this build produces is named after it.
workload_basename(Basename):-
    workload_source(Source),
    file_base_name(Source, BasenameWithExtension),
    file_name_extension(Basename, _Extension, BasenameWithExtension).

% ==============================================================================
%!  filename_suffix(Feature, Suffix).
%       How each feature that distinguishes one artifact from another is spelled
%       in a filename.
filename_suffix(static, '_static').
filename_suffix(aot,    '_aot').

% ==============================================================================
%!  step_basename(Step, Basename).
%       Succeeds when Basename is the name of the file the step writes, without
%       an extension. An AOT step names its output after the file it reads, plus
%       its own suffix.
step_basename(aot(_, Step), Basename):-
    step_basename(Step, InputBasename),
    filename_suffix(aot, Suffix),
    atomic_list_concat([InputBasename, Suffix], Basename).

step_basename(compile(_, _, Modifiers), Basename):-
    workload_basename(InputBasename),
    findall(Suffix,
                ( member(Modifier, Modifiers),
                  filename_suffix(Modifier, Suffix) ),
            Suffixes),
    atomic_list_concat([InputBasename|Suffixes], Basename).

% ==============================================================================
%!  step_filename(Step, Filename).
%       Succeeds when Filename is the full name of the file the step writes,
%       extension included. The RUN command writes it and the next stage
%       copies it.
step_filename(Step, Filename):-
    step_basename(Step, Basename),
    step_code_format(Step, CodeFormat),
    findall(Extension, artifact_extension(CodeFormat, Extension), Extensions),
    atomic_list_concat([Basename|Extensions], Filename).

% ==============================================================================
%!  language_runner(Language, Path).
%       The header Path that defines main for a workload written in Language.
language_runner(c, 'src/workload_runner.h').

% ==============================================================================
%!  step_input(Step, Input).
%       Succeeds when Input is a file the step needs before it can run. A
%       compile step reads the workload source and its language's runner. An AOT
%       step reads the file its input step wrote, which another stage holds.
step_input(compile(_,_,_), source(Path, Filename)):-
    workload_language(Language),
    language_runner(Language, Path),
    file_base_name(Path, Filename).

step_input(compile(_,_,_), source(Path, Filename)):-
    workload_source(Path),
    file_base_name(Path, Filename).

step_input(aot(_, InputStep), artifact(Toolchain, Filename)):-
    step_toolchain(InputStep, Toolchain),
    step_filename(InputStep, Filename).

% ==============================================================================
%!  stage_inputs(Toolchain, Inputs).
%       Succeeds when Inputs is every file the stage must copy in before its
%       steps run. One answer per builder stage. Two steps that read the same
%       file copy it once.
stage_inputs(Toolchain, Inputs):-
    setof(Input, Step^Steps^( stage_steps(Toolchain, Steps),
                              member(Step, Steps),
                              step_input(Step, Input) ),
          Inputs).

% ==============================================================================
%!  stage_order(Toolchains).
%       Succeeds when Toolchains lists every builder stage in an order where a
%       stage appears after every stage it copies an artifact from. A build
%       graph with a cycle has no such order and no answer here.
stage_order(Toolchains):-
    findall(Toolchain, stage_steps(Toolchain, _), Vertices),
    findall(Producer-Consumer,
            ( stage_inputs(Consumer, Inputs),
              member(artifact(Producer, _), Inputs) ),
            Edges),
    vertices_edges_to_ugraph(Vertices, Edges, Graph),
    top_sort(Graph, Toolchains).

% ==============================================================================
%!  target_shipped_filename(Target, Filename).
%       Succeeds when Filename is the file that ends up in the final image,
%       produced by the target's last build step.
target_shipped_filename(Target, Filename):-
    target_last_step(Target, Step),
    step_filename(Step, Filename).

% ==============================================================================
%!  target_entrypoint(Target, Path).
%       Succeeds when Path is the absolute path of the artifact inside the final
%       image.
target_entrypoint(Target, Path):-
    target_shipped_filename(Target, Filename),
    atomic_list_concat(['/', Filename], Path).

% ==============================================================================
%!  target_self_contained(Target).
%       Succeeds when the target is a self-contained executable (static and wasm
%       targets).
target_self_contained(Target):-
    link_mode(Target, static).

target_self_contained(Target):-
    code_format(Target, wasm).

% ==============================================================================
%!  target_base_image(Target, Base).
%       Succeeds when Base is what the target's final image sits on. Either
%       scratch or a distro image. Only dynamic linking needs a distro.
target_base_image(Target, scratch):-
    target_self_contained(Target).

target_base_image(Target, 'debian:trixie-slim'):-
    link_mode(Target, 'dynamic').

% ==============================================================================
%!  optimization_syntax(Toolchain, Prefix).
%       How each toolchain spells the optimization level.
optimization_syntax(gcc,        '-O').
optimization_syntax(wasi_sdk,   '-O').
optimization_syntax(wasmedge,   '--optimize ').
optimization_syntax(rustc,      '-C opt-level=').
optimization_syntax(rustc_wasm, '-C opt-level=').

% ==============================================================================
%!  optimization_flag(Toolchain, Flag).
%       Succeeds when Flag is the optimization flag for the given toolchain at
%       the given optimization level.
optimization_flag(Toolchain, Flag):-
    optimization_syntax(Toolchain, Prefix),
    optimization_level(Level),
    atomic_list_concat([Prefix, Level], Flag).

% ==============================================================================
%!  toolchain_binary(Toolchain, Binary).
%       The command that invokes each toolchain. The wasi-sdk image exports $CC,
%       so the Dockerfile does not name the clang inside it.
toolchain_binary(gcc,      gcc).
toolchain_binary(rustc,    rustc).
toolchain_binary(rustc_wasm, rustc).
toolchain_binary(wasi_sdk, '$CC').
toolchain_binary(wasmedge, 'wasmedge').

% ==============================================================================
%!  toolchain_flag(Toolchain, Flag).
%       Flags this project passes on every build with the toolchain, whatever
%       the target.
toolchain_flag(gcc,      '-s').
toolchain_flag(rustc,    '-C strip=symbols').
toolchain_flag(rustc_wasm, '-C strip=symbols').
toolchain_flag(rustc_wasm, '--target wasm32-wasip1').
toolchain_flag(wasi_sdk, '-Wl,--strip-all').

% ==============================================================================
%!  modifier_flag(Toolchain, Modifier, Flag).
%       How each toolchain spells each compile modifier.
modifier_flag(gcc, static, '-static').
modifier_flag(rustc, static, '-C target-feature=+crt-static').

% ==============================================================================
%!  step_command(Step, Command).
%       Succeeds when Command is the shell command the step runs, as one atom.
%       It follows RUN in the Dockerfile.
step_command(Step, Command):-
    Step = compile(Toolchain, _, Modifiers),
    toolchain_binary(Toolchain, Binary),
    optimization_flag(Toolchain, OptFlag),
    findall(Flag, toolchain_flag(Toolchain, Flag), ToolchainFlags),
    step_filename(Step, Filename),
    workload_source(SourcePath),
    file_base_name(SourcePath, SourceFilename),
    findall(Flag, ( member(Modifier, Modifiers),
                    modifier_flag(Toolchain, Modifier, Flag) ),
            ModifierFlags),
    append([ [Binary, OptFlag], ToolchainFlags, ModifierFlags,
             ['-o', Filename, SourceFilename] ], Words),
    atomic_list_concat(Words, ' ', Command).

step_command(Step, Command):-
    Step = aot(Toolchain, InputStep),
    toolchain_binary(Toolchain, Binary),
    optimization_flag(Toolchain, OptFlag),
    step_filename(Step, Filename),
    step_filename(InputStep, InputFilename),
    atomic_list_concat([Binary, compile, OptFlag, InputFilename, Filename],
                       ' ', Command).

