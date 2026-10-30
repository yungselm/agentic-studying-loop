# Migrating a deck built with rust-lang-kata's old scripts

The engine keeps rust-lang-kata's note types (same model ids and fields), so existing Anki
notes and their review history carry over. rust-lang-kata itself was migrated this way
(commit "Build with agentic-studying-loop"): same GUIDs, deck names, presets and NeetCode
order as the old `build.py`.

## Steps for a card folder

1. Put a `deck.yaml` next to the card files, in their **current** location and with their
   current file names (the old GUIDs are derived from the file name):
   ```yaml
   deck: "Rust Language Kata::Core"
   pack: rust
   prefix: rlk
   guid: legacy-kata            # reproduce the old front-text GUIDs
   # legacy_additional: true    # only for files from additional_cards/ (GUIDs were namespaced)
   ```
2. `asl fix <folder>`: writes an `id:` for every card **and** freezes its current GUID as
   `guid:`. Compare with an old build if you like: `asl build <folder>` must give the same
   GUIDs.
3. Remove `guid: legacy-kata`. From now on files can be renamed or moved and fronts edited;
   cards update in place.
4. Optional: presets with `conf_id: 1001` / `1002` and `name:` keep the old options groups;
   numbered file names (`01_arrays_hashing.yaml`) keep an ordered subdeck list.

## Project cards staged in a vault (e.g. omakase.yaml / omakase_crates.yaml)

These were built as kata "additional" cards. Put both files in one deck folder in your card
home with:

```yaml
deck: "Rust Language Kata::Additional::Omakase"
pack: rust
prefix: omk
subdecks: false
guid: legacy-kata
legacy_additional: true
repo: "C:/path/to/omakase"      # enables header / excerpt / drift checks
files:
  omakase_crates.yaml: {check: false}
```

Then `asl fix` as above: the `# omk-001` comment ids become `id:` fields (the crates file keeps
its `omc-` ids; lint notes the different prefix, which is fine). Split the old standards file
into `standards/core.md` + `rust.md` + `preferences.md`; project tables go into the deck's
`profile.md`.

Note: a deck folder whose name differs from the old file stem still works, because the GUID
uses the file name, not the folder; but after `asl fix` nothing depends on names any more.
