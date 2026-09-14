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
%!  malformed_values(Section, SectionDict, MalformedValueKeysList).
%       Succeeds when MalformedValueKeysList holds the section's keys whose
%       values do not match their key_pattern/3. Empty when the section is
%       clean.
malformed_values(Section, SectionDict, MalformedValueKeysList):-
    findall(Key, ( key_pattern(Section, Key, Pattern),
                   get_dict(Key, SectionDict, Value),
                   format(string(Text), '~w', [Value]),
                   \+ re_match(Pattern, Text) ),
                MalformedValueKeysList).

% ==============================================================================
%!  value_shape(Value, Shape).
%       Succeeds when Shape is the shape of one parsed YAML value (list,
%       mapping, or scalar).
value_shape(Value, list):-
    is_list(Value), !.

value_shape(Value, mapping):-
    is_dict(Value), !.

value_shape(Value, scalar):-
    not(is_list(Value)), not(is_dict(Value)), !.

% ==============================================================================
%!  key_shape(Section, Key, Shape).
%       The keys whose value is not a scalar. A key with no row here is scalar.
key_shape(config, workload, mapping).
key_shape(config, build, mapping).
key_shape(config, targets, list).

% ==============================================================================
%!  key_expected_shape(Section, Key, Shape).
%       Succeeds when Shape is the shape a key's value must have: its
%       key_shape/3 row, or scalar when it has none.
key_expected_shape(Section, Key, Shape):-
    key_shape(Section, Key, Shape).

key_expected_shape(Section, Key, scalar):-
    not(key_shape(Section, Key, _)).

% ==============================================================================
%!  misshapen_values(Section, SectionDict, MisshapenValueKeysList).
%       Succeeds when MisshapenValueKeysList holds the section's keys whose
%       values do not have their key_expected_shape/3. Empty when the section
%       is clean.
misshapen_values(Section, SectionDict, MisshapenValueKeysList):-
    findall(Key, (get_dict(Key, SectionDict, Value),
                  value_shape(Value, Shape),
                  not(key_expected_shape(Section, Key, Shape))),
                MisshapenValueKeysList).

% ==============================================================================
%!  report_keys(Label, Fault, Keys).
%       Prints one line naming the bad keys. Prints nothing when the list is
%       empty, so a section with only one kind of fault gets only one line.
%       Fault is the phrase before the keys, such as 'unknown keys' or
%       'malformed values in'.
report_keys(_, _, []).
report_keys(Label, Fault, [Key|Keys]):- % at least one key
    format(user_error, '~w has ~w: ~w~n', [Label, Fault, [Key|Keys]]).

% ==============================================================================
%!  valid_section(Label, Section, SectionDict).
%       Succeeds when the section is a mapping with no unknown or missing keys
%       and no malformed or misshapen values. Otherwise reports what is wrong
%       and fails, with Label naming the error's location in the file. The two
%       argument form uses the section name as the label.
valid_section(Section, SectionDict):-
    valid_section(Section, Section, SectionDict).

valid_section(Label, _, SectionDict):-
    not(is_dict(SectionDict)),
    format(user_error, '~w is not a mapping~n', [Label]),
    !, fail.

valid_section(_, Section, SectionDict):-
    unknown_keys(Section, SectionDict, []),
    missing_keys(Section, SectionDict, []),
    malformed_values(Section, SectionDict, []),
    misshapen_values(Section, SectionDict, []),
    !.

valid_section(Label, Section, SectionDict):-
    unknown_keys(Section, SectionDict, UnknownKeys),
    missing_keys(Section, SectionDict, MissingKeys),
    misshapen_values(Section, SectionDict, MisshapenValueKeys),
    malformed_values(Section, SectionDict, MalformedValueKeys),
    report_keys(Label, 'unknown keys', UnknownKeys),
    report_keys(Label, 'missing keys', MissingKeys),
    subtract(MisshapenValueKeys, UnknownKeys, ReportedMisshapenValueKeys),
    report_keys(Label, 'misshapen values in', ReportedMisshapenValueKeys),
    subtract(MalformedValueKeys, MisshapenValueKeys, ReportedMalformedValueKeys),
    report_keys(Label, 'malformed values in', ReportedMalformedValueKeys),
    fail.

% ==============================================================================
%!  valid_targets(Targets).
%       Succeeds when Targets is a non-empty list and every target in it is
%       valid. The label is the target's index, so a message says which target
%       is wrong. It cannot be the target's name, because a missing name is one
%       of the errors.
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
%!  parsed_config(Path, Config).
%       Succeeds when Config is the parsed content of the file at Path.
%       Otherwise reports what went wrong and fails.
parsed_config(Path, Config):-
    catch(yaml_read(Path, Config), error(Error, _),
          ( format(user_error, 'cannot read ~w: ~w~n', [Path, Error]),
            fail )).

% ==============================================================================
%!  read_config(Path, Facts).
%       Reads the file at Path and returns the facts it declares. Fails if the
%       file does not pass valid_config/1, and then returns nothing. This means
%       a bad file can't load half-way.
read_config(Path, Facts):-
    parsed_config(Path, Config),
    valid_config(Config),
    workload_section_facts(Config, WorkloadFacts),
    build_section_facts(Config, BuildFacts),
    targets_section_facts(Config, TargetsFacts),
    append([WorkloadFacts, BuildFacts, TargetsFacts], Facts).
