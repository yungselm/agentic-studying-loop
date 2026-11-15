"""Text-to-speech, the fallback when a card has no native audio (a book example, a deck without
clips). Engines from the language config, tried in order:

  voicevox  a local VOICEVOX engine (http://127.0.0.1:50021), Japanese, offline
  edge      Microsoft Edge's online neural voices (`edge-tts`, in the `lang` extra); the text is
            sent to Microsoft

Cards get `tts: true`; the build tags them `asl::tts`, so stats can compare them with native audio."""
from __future__ import annotations

import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from .tokens import plain_text


def _voicevox(text: str, out: Path, cfg: dict) -> bool:
    url = str(cfg.get("voicevox_url") or "http://127.0.0.1:50021").rstrip("/")
    speaker = int(cfg.get("voicevox_speaker") or 3)
    try:
        q = urllib.parse.urlencode({"text": text, "speaker": speaker})
        with urllib.request.urlopen(urllib.request.Request(f"{url}/audio_query?{q}", method="POST"),
                                    timeout=30) as r:
            query = r.read()
        req = urllib.request.Request(f"{url}/synthesis?speaker={speaker}", data=query, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            wav = r.read()
    except Exception:
        return False                          # not running: next engine
    from .audio import ffmpeg_exe
    tmp = out.with_suffix(".wav")
    tmp.write_bytes(wav)
    try:
        subprocess.run([ffmpeg_exe() or "ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-q:a", "4", str(out)], check=True)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def _edge(text: str, out: Path, cfg: dict) -> bool:
    try:
        import asyncio

        import edge_tts
    except ImportError:
        return False
    try:
        asyncio.run(edge_tts.Communicate(text, str(cfg.get("edge_voice") or "ja-JP-NanamiNeural"))
                    .save(str(out)))
    except Exception:
        return False
    return out.is_file() and out.stat().st_size > 0


ENGINES = {"voicevox": _voicevox, "edge": _edge}


def synthesize(text: str, out: Path, cfg: dict) -> str | None:
    """Speak `text` into `out` (.mp3) with the first engine that works; its name, or None."""
    tts = cfg.get("tts") or {}
    out.parent.mkdir(parents=True, exist_ok=True)
    for name in tts.get("engines") or ["voicevox", "edge"]:
        if name in ENGINES and ENGINES[name](text, out, tts):
            return name
    return None


def fill_audio(d) -> int:
    """Every sentence/grammar card without `audio:` gets a TTS clip (media_dir/tts/<id>.mp3)."""
    from ..cards import load_file
    from ..config import load_deck
    from .cardfile import edit_cards
    deck = load_deck(d.path)
    done, failed, changes = [], [], {}
    for f in deck.files():
        for c in load_file(f):
            if c.get("type") not in ("sentence", "grammar") or not c.get("id") \
                    or str(c.get("audio") or "").strip():
                continue
            name = f"tts_{c['id']}.mp3"
            engine = synthesize(plain_text(str(c.get("text") or "")).replace(" ", ""),
                                d.media_dir / "tts" / name, d.cfg)
            if not engine:
                failed.append(str(c["id"]))
                continue
            changes[str(c["id"])] = {"audio": name, "tts": engine}
            done.append(f"{c['id']} ({engine})")
    edit_cards(d.path, "id", changes)
    print(f"TTS: {len(done)} card(s) got audio" + (f": {', '.join(done)}" if done else ""))
    if failed:
        print(f"  ! no engine worked for {', '.join(failed)}: start VOICEVOX, or install edge-tts "
              "(part of the `lang` extra) and check the network")
    return 1 if failed else 0
