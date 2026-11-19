# Install

## 1. uv

`asl` installs as a uv tool. Skip this if `uv --version` works.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh                                    # macOS / Linux / WSL
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows
```

Then open a new terminal.

## 2. asl

```bash
uv tool install "agentic-studying-loop[python,analysis] @ https://github.com/yungselm/agentic-studying-loop/archive/refs/heads/master.zip"
asl packs        # lists cpp, python, rust; if `asl` isn't found: uv tool update-shell
```

Update later with the same command plus `--force`.

The extras in brackets are optional; pick what you need:

| Extra | Adds |
|---|---|
| `python` | `asl check` for Python cards (pytest, ruff) |
| `analysis` | `asl stats`: review data, reports, figures (pandas, matplotlib) |
| `lang` | language decks, `asl lang` (word frequencies, ffmpeg, text-to-speech) |
| `lang-ja` | `lang` + Japanese (UniDic tokenizer) |
| `lang-de` | `lang` + German (spaCy and its small German model) |

Rust cards also need [Rust](https://rustup.rs/) with `rustup component add clippy`. C++ cards need
`g++` or `clang++`; `clang-tidy` adds the Core Guidelines checks.

## 3. A card home

The folder where all your decks live. With a notes vault (any folder of Markdown, e.g. Obsidian):

```bash
asl init-home "<vault>/Anki cards" --vault "<vault>"
```

Cards only, no notes:

```bash
asl init-home "<folder>" --no-vault
```

## 4. Skills for the agent

```bash
asl install-skills
```

Installs the Claude Code skills of the modules you installed (e.g. `language-cards` only with
`lang`).

## 5. Check it works

Connect a project or topic (`asl init`, `asl topic`; see the README), then:

```bash
asl lint -q "<card home>/<deck>"     # prints OK
asl build "<card home>/<deck>" -o deck.apkg
```

Import `deck.apkg` in Anki via File → Import, with **Update notetypes** ticked.
