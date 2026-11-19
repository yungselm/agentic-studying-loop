"""German word levels: CEFR estimated from general frequency (wordfreq), since no official
German word list is free to use. A word's level is the first band its rank falls in
(`levels: bands:` in de.yaml); every level reads as an estimate (`~A2`)."""
from __future__ import annotations

from studyloop.language.vocabulary.levels import NONE, Levels


class DeLevels(Levels):
    def __init__(self, cfg: dict):           # no list files: frequency bands only
        lv = cfg.get("levels") or {}
        self.order = list(lv.get("order") or [])
        self.bands = {k: int(v) for k, v in (lv.get("bands") or {}).items()}
        self.by_word, self.by_reading, self.by_variant, self.medians = {}, {}, {}, {}
        self.rank = {}
        try:
            import wordfreq
            self.rank = {w: i + 1 for i, w in enumerate(wordfreq.iter_wordlist(cfg["code"]))}
        except ImportError:
            pass

    def level(self, forms: list[str], reading: str) -> str:
        r = self.frequency_rank([f.lower() for f in forms])      # wordfreq's list is lower case
        if r is None:
            return NONE
        return next(("~" + lvl for lvl in self.order if r <= self.bands.get(lvl, 0)), NONE)
