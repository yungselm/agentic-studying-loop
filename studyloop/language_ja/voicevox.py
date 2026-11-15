"""VOICEVOX: a local text-to-speech engine for Japanese (http://127.0.0.1:50021), offline."""
from __future__ import annotations

import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from ..language.audio import ffmpeg_exe


def speak(text: str, out: Path, cfg: dict) -> bool:
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
    tmp = out.with_suffix(".wav")
    tmp.write_bytes(wav)
    try:
        subprocess.run([ffmpeg_exe() or "ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-q:a", "4", str(out)], check=True)
    finally:
        tmp.unlink(missing_ok=True)
    return True
