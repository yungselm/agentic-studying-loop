"""Text-to-speech, the fallback when a card has no native audio (a book example, a deck without
clips). Engines from the language config (`tts: engines:`), tried in order:

  edge      Microsoft Edge's online neural voices (`edge-tts`, in the `lang` extra; `edge_voice:`
            in the config); the text is sent to Microsoft
  ...       the language's own (`Language.tts_engines`; Japanese: a local VOICEVOX)

Cards get `tts: true`; the build tags them `asl::tts`, so stats can compare them with native audio."""
from __future__ import annotations

from pathlib import Path

from studyloop.language.vocabulary.tokens import plain_text


def _edge(text: str, out: Path, cfg: dict) -> bool:
    try:
        import asyncio

        import edge_tts
    except ImportError:
        return False
    try:
        voice = str(cfg.get("edge_voice") or "")
        if not voice:
            return False
        asyncio.run(edge_tts.Communicate(text, voice).save(str(out)))
    except Exception:
        return False
    return out.is_file() and out.stat().st_size > 0


ENGINES = {"edge": _edge}             # shared by every language


def synthesize(text: str, out: Path, cfg: dict, engines: dict | None = None) -> str | None:
    """Speak `text` into `out` (.mp3) with the first engine that works; its name, or None."""
    engines = {**ENGINES, **(engines or {})}
    tts = cfg.get("tts") or {}
    out.parent.mkdir(parents=True, exist_ok=True)
    for name in tts.get("engines") or list(engines):
        if name in engines and engines[name](text, out, tts):
            return name
    return None


def fill_audio(d) -> int:
    """Every sentence/grammar card without `audio:` gets a TTS clip (media_dir/tts/<id>.mp3)."""
    from studyloop.core.cards import load_file
    from studyloop.core.config import load_deck
    from studyloop.language.cards.io import edit_cards
    deck = load_deck(d.path)
    done, failed, changes = [], [], {}
    for f in deck.files():
        for c in load_file(f):
            if c.get("type") not in ("sentence", "grammar") or not c.get("id") \
                    or str(c.get("audio") or "").strip():
                continue
            name = f"tts_{c['id']}.mp3"
            engine = synthesize(plain_text(str(c.get("text") or "")).replace(" ", ""),
                                d.media_dir / "tts" / name, d.cfg, d.language.tts_engines())
            if not engine:
                failed.append(str(c["id"]))
                continue
            changes[str(c["id"])] = {"audio": name, "tts": engine}
            done.append(f"{c['id']} ({engine})")
    edit_cards(d.path, "id", changes)
    print(f"TTS: {len(done)} card(s) got audio" + (f": {', '.join(done)}" if done else ""))
    if failed:
        print(f"  ! no engine worked for {', '.join(failed)}: check the engines in the language "
              "config (`tts:`), e.g. start VOICEVOX, or install edge-tts and check the network")
    return 1 if failed else 0
