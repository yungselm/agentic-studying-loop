"""Word levels: official/curated lists first, else an estimate from general frequency.

Level strings: "N4" (on a list), "~N3" (estimated from frequency rank), "—" (neither)."""
from __future__ import annotations

import csv
import io
import math
import os
import statistics
import sys
import urllib.request
from pathlib import Path

import yaml

from .tokens import hira

HERE = Path(__file__).resolve().parent
NONE = "—"


def lang_config(code: str) -> dict:
    p = HERE / f"{code}.yaml"
    if not p.is_file():
        have = ", ".join(sorted(q.stem for q in HERE.glob("*.yaml")))
        raise SystemExit(f"No language config for '{code}' (have: {have})")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg["code"] = code
    return cfg


def cache_dir(code: str) -> Path:
    base = os.environ.get("ASL_CACHE") or os.environ.get("XDG_CACHE_HOME") or (
        os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else None)
    root = Path(base) if base else Path.home() / ".cache"
    d = (root if os.environ.get("ASL_CACHE") else root / "asl") / "lang" / code
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup(code: str, force: bool = False) -> int:
    """Download the level lists into the cache."""
    cfg = lang_config(code)
    lists = (cfg.get("levels") or {}).get("lists") or {}
    d = cache_dir(code)
    for level, url in lists.items():
        out = d / f"level_{level}.csv"
        if out.exists() and not force:
            print(f"  {level}: cached ({out})")
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "agentic-studying-loop"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out.write_bytes(r.read())
        print(f"  {level}: downloaded → {out}")
    if credit := (cfg.get("levels") or {}).get("credit"):
        print(f"  ({credit})")
    try:
        import wordfreq  # noqa: F401
    except ImportError:
        print("  ! wordfreq missing: pip install wordfreq (frequency estimates are skipped)")
    return 0


class Levels:
    """Look up a word's level; estimate unlisted words from frequency rank."""

    def __init__(self, cfg: dict):
        lv = cfg.get("levels") or {}
        self.order: list[str] = list(lv.get("order") or [])
        self.by_word: dict[str, str] = {}
        self.by_kana: dict[str, str] = {}
        self.by_skeleton: dict[tuple[str, str], str] = {}   # (kanji only, reading): 付き合う = 付合う
        d = cache_dir(cfg["code"])
        missing = [lvl for lvl in self.order if not (d / f"level_{lvl}.csv").exists()]
        if missing:
            raise SystemExit(f"Level lists not downloaded: run `asl lang setup {cfg['code']}`")
        for lvl in reversed(self.order):          # easiest level wins: written last
            text = (d / f"level_{lvl}.csv").read_text(encoding="utf-8-sig")
            for row in csv.DictReader(io.StringIO(text)):
                expr, reading = (row.get("expression") or "").strip(), hira((row.get("reading") or "").strip())
                for form in filter(None, (s.strip() for s in expr.replace("；", ";").split(";"))):
                    self.by_word[form] = lvl
                    if reading and (sk := _skeleton(form)):
                        self.by_skeleton[(sk, reading)] = lvl
                if reading:
                    self.by_kana[reading] = lvl
        self.rank: dict[str, int] = {}
        if cfg.get("frequency") == "wordfreq":
            try:
                import wordfreq
                self.rank = {w: i + 1 for i, w in enumerate(wordfreq.iter_wordlist(cfg["code"]))}
            except ImportError:
                pass
        self.medians = self._calibrate()

    def _calibrate(self) -> dict[str, float]:
        """Median log-rank of the listed words per level: the bands for estimates."""
        logs: dict[str, list[float]] = {lvl: [] for lvl in self.order}
        for w, lvl in self.by_word.items():
            if w in self.rank:
                logs[lvl].append(math.log(self.rank[w]))
        return {lvl: statistics.median(v) for lvl, v in logs.items() if v}

    def listed(self, forms: list[str], reading: str) -> str | None:
        for f in forms:
            if f in self.by_word:
                return self.by_word[f]
        for f in forms:
            if (sk := _skeleton(f)) and (sk, reading) in self.by_skeleton:
                return self.by_skeleton[(sk, reading)]
        if all(_is_kana(f) for f in forms) and reading in self.by_kana:
            return self.by_kana[reading]
        return None

    def frequency_rank(self, forms: list[str]) -> int | None:
        ranks = [self.rank[f] for f in forms if f in self.rank]
        return min(ranks) if ranks else None

    def level(self, forms: list[str], reading: str) -> str:
        if lvl := self.listed(forms, reading):
            return lvl
        r = self.frequency_rank(forms)
        if r is None or not self.medians:
            return NONE
        lr = math.log(r)
        hardest = self.order[-1]
        if hardest in self.medians and lr > self.medians[hardest] + 1.0:   # far rarer than the hardest list
            return NONE
        best = min(self.medians, key=lambda lvl: abs(self.medians[lvl] - lr))
        return "~" + best

    def sort_index(self, level: str, current: str | None) -> int:
        """0 = at or below the current level; then one step per level above; unknown last."""
        base = level.lstrip("~")
        if base not in self.order:
            return len(self.order) + 1
        i = self.order.index(base)
        cur = self.order.index(current) if current in self.order else -1
        return max(0, i - cur)


def _skeleton(s: str) -> str:
    """The kanji of a word without its kana (okurigana): 付き合う, 付合う -> 付合."""
    return "".join(c for c in s if not _is_kana(c))


def _is_kana(s: str) -> bool:
    return all("ぁ" <= c <= "ゖ" or "ァ" <= c <= "ヺ" or c == "ー" for c in s)
