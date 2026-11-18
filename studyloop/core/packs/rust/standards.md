# Rust addendum

- `asl check` puts each card's `solution` in its own module (items: `fn`, `struct`, `impl`; no
  `main`), its `tests:` in a `#[test] fn` with `use super::*`, and a concept's `code:` in the body
  of a `fn` (statements). The `starter` is not compiled.
- Solutions match `rustfmt`; checked files compile on stable (edition in `pack.yaml`, default 2021: no let chains) under `clippy -D warnings`. A needed `#[allow(..)]` goes on the item, reason in `notes`.
- Comments: elision `// ...`, header `// src/<path>  (<role>)`, hint `// uses: ...`, stubs `// stubs (real: src/<file>)`.
- Starter data: concurrency/async code cards failed 32% vs 19%; `Poll`/`Waker`/`Pin`/toy executors sat at difficulty 8.7–9.9. Use timelines and gap cards on real `tokio`/`std::thread` code.
- Borrow-checker errors make good debugging cards: error code + symptom on the front, cause + fix in one bold sentence.
- Third-party crates go in the `_ext` file.
