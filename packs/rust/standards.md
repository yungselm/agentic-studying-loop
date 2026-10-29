# Rust addendum

Read after `core.md`; `preferences.md` wins over both.

- **Formatting:** solutions match `rustfmt` defaults (and the repo's `rustfmt.toml` for project cards).
- **Checked files compile on stable with the edition in `pack.yaml`** (default 2021, so no let chains)
  under `clippy -D warnings`. A card that needs a lint exception says so in a `#[allow(..)]` on the
  item, with the reason in `notes`.
- **Comments:** elisions `// ...`, location header `// src/<path>  (<role>)`, hints `// uses: ...`,
  stubs under `// stubs (real: src/<file>)`.
- **Hard topics in the starter data:** concurrency and async code cards failed 32% vs 19%; `Poll`,
  `Waker`, `Pin` and toy executors sat at difficulty 8.7–9.9. Use timelines and gap cards on real
  `tokio`/`std::thread` code, not hand-rolled futures.
- **Borrow-checker errors** make good debugging cards: the error code and the symptom on the front,
  cause + fix in one bold sentence.
- **Third-party crates** (`tokio`, `serde`, GUI frameworks…) go in the `_ext` file (`check: false`).
