# Migrating from rust-lang-kata

The engine keeps rust-lang-kata's note types (same model ids and fields), so existing Anki
notes and their review history carry over. Do this on a branch; nothing changes in Anki until
you import.

## A deck folder (e.g. the core cards)

1. Add a `deck.yaml` next to the card files:
   ```yaml
   deck: "Rust Language Kata::Core"
   pack: rust
   prefix: rlk
   guid: legacy-kata          # reproduce the old front-text GUIDs for now
   ```
   For NeetCode-style files, use `files:` / `order:` / a `sequential` preset (see card-format.md).
2. `asl build <folder> -o test.apkg` and compare note GUIDs with the old build: they must match
   (they did for the tested files).
3. `asl ids <folder> --fix`: writes `id:` fields **and** freezes each card's current GUID as
   `guid:`. Remove `guid: legacy-kata` from deck.yaml. From now on, front edits update cards in
   place.
4. Import with "Update notetypes" ticked.

## Project staging files (e.g. omakase.yaml / omakase_crates.yaml)

These were built as kata "additional" cards. Put both files in one folder with:

```yaml
deck: "Rust Language Kata::Additional::Omakase"
pack: rust
prefix: omk
subdecks: false
guid: legacy-kata
legacy_additional: true       # old GUIDs were namespaced additional__<stem>
files:
  omakase_crates.yaml: {check: false}
```

Then `asl ids --fix` as above (the `# omk-001` comment ids become `id:` fields; the crates file
keeps its `omc-` ids). Move the vault's standards file to `standards/core.md` + `rust.md` +
`preferences.md` (project-specific tables go to the deck's `profile.md`).

## The kata repo itself

Once the engine is stable, the kata can depend on it: keep `cards/`, replace `build.py`,
`check_cards.py`, `lint_cards.py`, `templates/`, `vendor/` with `asl` calls and a `deck.yaml`.
