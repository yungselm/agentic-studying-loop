# Decks, cards and review data

What most modules read: deck folders, card files, the card home and Anki exports.

## Decks

```{eval-rst}
.. autoclass:: studyloop.core.config.Deck
   :members:

.. autofunction:: studyloop.core.config.load_deck

.. autofunction:: studyloop.core.config.resolve_inputs
```

## The card home

```{eval-rst}
.. autoclass:: studyloop.core.config.Home
   :members:

.. autofunction:: studyloop.core.config.find_home
```

## Card files

```{eval-rst}
.. autofunction:: studyloop.core.cards.load_file

.. autoexception:: studyloop.core.cards.CardFileError
```

## Anki exports

```{eval-rst}
.. autofunction:: studyloop.core.anki.read_export

.. autoclass:: studyloop.core.anki.ReviewData
   :members: read_media, extract_media
```

