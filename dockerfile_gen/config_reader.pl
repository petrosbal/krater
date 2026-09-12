%%% config_reader.pl
%%%
%%% Part #1 of the Dockerfile generator pipeline.
%%% Reads build.yaml, checks it, and returns its content as Prolog facts.

:- module(config_reader, [read_config/2]).
:- use_module(library(yaml)).
:- use_module(library(pcre)).

% ==============================================================================
%!  required_key(Section, Key).
%       The keys a section must contain. Everything in allowed_key/2 but not
%       here is optional.
required_key(config, workload).
required_key(config, build).
required_key(config, targets).
required_key(target, name).
required_key(target, code_format).
required_key(workload, language).
required_key(workload, source).
required_key(build, optimization_level).

% ==============================================================================
%!  allowed_key(Section, Key).
%       Every key a section of build.yaml may contain. Anything else is a typo.
%       The facts are the optional keys. The rule adds every required key.
allowed_key(target, link_mode).
allowed_key(target, aot_compiler).
allowed_key(Section, Key):-
    required_key(Section, Key).

% ==============================================================================
%!  unknown_keys(Section, SectionDict, UnknownKeysList).
%       Succeeds when UnknownKeysList holds the section's keys that
%       allowed_key/2 does not name. Empty when the section is clean.
unknown_keys(Section, SectionDict, UnknownKeysList):-
    dict_keys(SectionDict, Keys),
    findall(Key, (member(Key, Keys),
                  not(allowed_key(Section, Key))),
                 UnknownKeysList).

% ==============================================================================
%!  missing_keys(Section, SectionDict, MissingKeysList).
%       Succeeds when MissingKeysList holds the section's required_key/2 keys
%       that it does not declare. Empty when the section is clean.
missing_keys(Section, SectionDict, MissingKeysList):-
    dict_keys(SectionDict, Keys),
    findall(Key, (required_key(Section, Key),
                  not(member(Key, Keys))),
                MissingKeysList).

% ==============================================================================
%!  key_pattern(Section, Key, Pattern).
%       The regex a key's value must match in full. A key with no row here
%       accepts any value.
key_pattern(target,   name,   "^[a-z][a-z0-9]*(?:(?:[._]|__|-+)[a-z0-9]+)*\\z").
key_pattern(workload, source,               "^[A-Za-z0-9_][A-Za-z0-9._/-]*\\z").
key_pattern(build,    optimization_level,                          "^[0-3]\\z").

% ==============================================================================
%!  malformed_keys(Section, SectionDict, MalformedKeysList).
%       Succeeds when MalformedKeysList holds the section's keys whose values
%       do not match their key_pattern/3. Empty when the section is clean.
malformed_keys(Section, SectionDict, MalformedKeysList):-
    findall(Key, ( key_pattern(Section, Key, Pattern),
                   get_dict(Key, SectionDict, Value),
                   format(string(Text), '~w', [Value]),
                   \+ re_match(Pattern, Text) ),
                MalformedKeysList).

% ==============================================================================
%!  report_keys(Label, Kind, Keys).
%       Prints one line naming the bad keys. Prints nothing when the list is
%       empty, so a section with only one kind of problem gets only one line.
%       The Kind argument is "unknown", "missing", or "malformed".
report_keys(_, _, []).
report_keys(Label, Kind, [Key|Keys]):-
    format(user_error, '~w has ~w keys: ~w~n', [Label, Kind, [Key|Keys]]).

% ==============================================================================
%!  valid_section(Label, Section, SectionDict).
%       Succeeds when the section is a mapping with no unknown, missing, or
%       malformed keys. Otherwise reports what is wrong and fails, with Label
%       naming the error's location in the file. The two argument form uses the
%       section name as the label.
valid_section(Section, SectionDict):-
    valid_section(Section, Section, SectionDict).

valid_section(Label, _, SectionDict):-
    not(is_dict(SectionDict)),
    format(user_error, '~w is not a mapping~n', [Label]),
    !, fail.

valid_section(_, Section, SectionDict):-
    unknown_keys(Section, SectionDict, []),
    missing_keys(Section, SectionDict, []),
    malformed_keys(Section, SectionDict, []),
    !.

valid_section(Label, Section, SectionDict):-
    unknown_keys(Section, SectionDict, UnknownKeys),
    missing_keys(Section, SectionDict, MissingKeys),
    malformed_keys(Section, SectionDict, MalformedKeys),
    report_keys(Label, unknown, UnknownKeys),
    report_keys(Label, missing, MissingKeys),
    report_keys(Label, malformed, MalformedKeys),
    fail.

% ==============================================================================
%!  valid_targets(Targets).
%       Succeeds when Targets is a non-empty list and every target in it is
%       valid. The label is the target's index, so a message says which target
%       is wrong. It cannot be the target's name, because a missing name is one
%       of the errors.
valid_targets(Targets):-
    not(is_list(Targets)),
    format(user_error, 'targets must be a list~n', []),
    !, fail.

valid_targets([]):-
    format(user_error, 'targets list must not be empty~n', []),
    !, fail.

valid_targets(Targets):-
    valid_targets(Targets, 1).

valid_targets([], _).
valid_targets([T|Ts], N):-
    atomic_list_concat(['target_', N], Label),
    valid_section(Label, target, T),
    N1 is N + 1,
    valid_targets(Ts, N1).

% ==============================================================================
%!  valid_target_names(Targets).
%       Succeeds when no two targets declare the same name. Otherwise reports
%       and fails. A repeated name asserts target/1 twice and makes every
%       attribute of that name nondeterministic, so the first entry silently
%       wins.
valid_target_names(Targets):-
    maplist(get_dict(name), Targets, Names),
    is_set(Names),
    !.

valid_target_names(_):-
    format(user_error, "target names must be unique~n", []),
    fail.

% ==============================================================================
%!  valid_config(Config).
%       Checks a parsed build.yaml for validity. Used by read_config/2.
valid_config(Config):-
    valid_section(config, Config),

    get_dict(workload, Config, Workload),
    valid_section(workload, Workload),

    get_dict(build, Config, Build),
    valid_section(build, Build),

    get_dict(targets, Config, Targets),
    valid_targets(Targets),
    valid_target_names(Targets).

% ==============================================================================
%!  target_key_fact(TargetName, TargetDict, Key, Fact).
%       Succeeds when Fact is what one key of a target declares. The YAML key
%       is also the functor, so there can be no drift. Fails when the key is
%       absent, which is what lets single_target_facts/2 treat optional keys
%       and required keys the same way.
target_key_fact(TargetName, TargetDict, Key, Fact):-
    get_dict(Key, TargetDict, String),
    atom_string(Value, String),
    Fact =.. [Key, TargetName, Value].

% ==============================================================================
%!  single_target_facts(TargetDict, Facts).
%       Succeeds when Facts is everything one target declares. The first is
%       target(Name), the rest are its attributes. A target with no link_mode
%       or AOT just gets a shorter list.
single_target_facts(TargetDict, Facts):-
    get_dict(name, TargetDict, TargetNameString),
    atom_string(TargetName, TargetNameString),
    findall(Fact,
            ( allowed_key(target, Key), Key \== name,
              target_key_fact(TargetName, TargetDict, Key, Fact) ),
            AttributeFacts),
    Facts = [target(TargetName)|AttributeFacts].

% ==============================================================================
%!  targets_section_facts(Config, Facts).
%       Succeeds when Facts is what every target in the targets list declares,
%       joined into one list.
targets_section_facts(Config, Facts):-
    get_dict(targets, Config, Targets),
    maplist(single_target_facts, Targets, ListOfLists),
    append(ListOfLists, Facts).

% ==============================================================================
%!  workload_section_facts(Config, Facts).
%       Succeeds when Facts is what the workload section declares. Both keys
%       get a prefix the YAML doesn't have, for clarity.
workload_section_facts(Config, Facts):-
    get_dict(workload, Config, Workload),
    get_dict(language, Workload, LanguageString),
    atom_string(Language, LanguageString),
    get_dict(source, Workload, SourceString),
    atom_string(Source, SourceString),
    Facts = [workload_language(Language), workload_source(Source)].

% ==============================================================================
%!  build_section_facts(Config, Facts).
%       Succeeds when Facts is what the build section declares.
build_section_facts(Config, Facts):-
    get_dict(build, Config, Build),
    get_dict(optimization_level, Build, Level),
    Facts = [optimization_level(Level)].

% ==============================================================================
%!  read_config(Path, Facts).
%       Reads the file at Path and returns the facts it declares. Fails if the
%       file does not pass valid_config/1, and then returns nothing. This means
%       a bad file can't load half-way.
read_config(Path, Facts):-
    yaml_read(Path, Config),
    valid_config(Config),
    workload_section_facts(Config, WorkloadFacts),
    build_section_facts(Config, BuildFacts),
    targets_section_facts(Config, TargetsFacts),
    append([WorkloadFacts, BuildFacts, TargetsFacts], Facts).
