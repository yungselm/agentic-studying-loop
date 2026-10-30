# Card format

A deck is a folder with a `deck.yaml` and one or more card files (`*.yaml`, each a YAML list).
Files starting with `_` are examples: checked and linted, but only built when passed by name.

## deck.yaml

```yaml
deck: "Study Loop::Tasklog"   # Anki deck for this folder
pack: python                  # default language (checker, highlighting, standards addendum)
prefix: tsk                   # ids: tsk-001, tsk-002, ...
repo: "../../code/tasklog"    # project source (makes it a project deck, see below)
subdecks: true                # true: <file stem> becomes a subdeck (a__b.yaml nests A::B)
check: true                   # default for all files
files:                        # per-file overrides
  tasklog_ext.yaml: {check: false}            # not compiled (third-party libraries)
  interview.yaml: {preset: slow, deck: "Interview"}   # own subdeck name / preset
order: [basics, advanced]     # file import order (= new-card order for sequential presets)
retired_ids: [tsk-007]        # deleted ids, never reused
presets:                      # Anki deck options written into the package
  default: {new_per_day: 14, order: random}
  slow: {new_per_day: 1, order: sequential, learning_steps: [1, 10], leech_fails: 5}
  # optional per preset: name (shown in Anki), conf_id (keep an existing options group)
guid: id                      # id (default) | legacy-kata (front-text GUIDs, for migration)
guid_namespace: asl-id        # GUID = hash(namespace, id): renaming decks/folders is safe; never reuse ids
```

## Card types

Common fields: `id` (stable, drives the Anki GUID), `std` (standards version it was written
under), `source`, `tags`, `lang` (override the deck's pack), `check: false`, `guid` (frozen GUID
from a migration), `lint_allow: ["literal"]`.

**code** (default): type the gap into an editor; on flip, lines that differ from the solution turn red.

```yaml
- id: tsk-001
  instruction: |    # observable behaviour + every literal the solution produces
  starter: |        # pre-filled editor content (the context frame, one gap)
  solution: |       # identical lines + the gap filled
  notes: |          # back side: the why
  tests: |          # asserts, run by `asl check` against the solution
  walkthrough: |    # optional step-through on the back (see rust-lang-kata)
```

**concept**: recall, then flip. The `**bold lead**` is what you grade yourself against.

```yaml
- id: tsk-003
  type: concept
  question: |       # code the question is about goes here, indented 4 spaces
  answer: |
    **Bold lead.** One or two sentences of detail.
  code: |           # optional, back side only, run by `asl check`
```

**timeline**: steps of a real flow, written in the right order; the build shuffles them (stable per
id), labels them A–E and makes the order the answer.

```yaml
- id: tsk-004
  type: timeline
  question: "Order what happens when save() runs:"
  steps: [first, second, third, fourth]
  detail: "One line on threads / who calls what."
```

## Project decks

A deck with `repo:` or a `profile.md` gets extra `asl lint` checks: every code section starts
with a location header whose path and role match `profile.md`; unchecked cards' code appears
verbatim and in order in the repo file the header names (`...` elisions and `uses:` hints
excepted); every card has an `Overview.md` row and a `std:`; `source: "<file> → <name>"` still
exists in the repo. `asl fix` adds missing ids, `std:` and index rows.

## Text formatting

`backticks` → inline code, `**bold**` → bold. Line breaks and indentation are kept.

## Tags added by the build

`asl::id::<id>`, `asl::std::v<N>`, `asl::type::<type>`: `asl stats` uses them to map review data
back to cards and to compare standards versions.
