"""What is done with cards: lint, build, check, plus the reading budget.

    lint.py     `asl lint`: checks every card needs (ids, duplicates, the deck's kind), then
                each card type's `lint`, then the lint rules modules register
    build.py    `asl build`: deck folders -> one .apkg (note types from the card types, media,
                deck presets, GUIDs from card ids)
    check.py    `asl check`: card code -> the pack's checker (compile, lint, tests)
    budget.py   tokens per word, batch size, splitting long sources into parts
"""
