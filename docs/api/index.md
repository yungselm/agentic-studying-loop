# API

## Using `asl`

- [Commands](cli.md): every command and option, with examples.
- [Card format](../card-format.md): what goes in `deck.yaml` and the card files.

## Writing a module

- [Registry](registry.md): the extension points (deck kinds, card types, lint rules, commands).
- [Decks, cards and review data](decks.md): what modules read.
- [Language interface](language.md) and [Analysis interface](analysis.md): the two
  extension points modules define for others.
- [Code map](map/index.md): each module's entry point, file by file.

```{toctree}
:hidden:
:maxdepth: 2

cli
../card-format
registry
decks
language
analysis
map/index
```
