# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 yungselm. Noncommercial use only; do not copy into other projects. See LICENSE.
"""Where the tool's own files live, paths from config files, and rewriting files as they were.

    PKG / ANKI          the shipped files (core's folder; Anki templates and vendored CodeMirror)
    native_path         `C:\\x` in WSL and `/mnt/c/x` on Windows: one vault serves both
    read_keep, write_keep   rewrite a file keeping its line endings and BOM
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

PKG = Path(__file__).resolve().parents[1]   # studyloop/core: everything core ships lives here
ANKI = PKG / "anki"                         # note-type templates + vendored CodeMirror


def native_path(s) -> Path:
    """A path from a config file, for this system: `C:\\x\\y` works in WSL (/mnt/c/x/y) and
    `/mnt/c/x/y` works on Windows (C:\\x\\y), so one vault serves both."""
    import re
    s = str(s).strip().strip('"')
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", s)
    if m and os.name != "nt" and Path(f"/mnt/{m.group(1).lower()}").is_dir():
        return Path(f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/"))
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", s)
    if m and os.name == "nt":
        return Path(f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\"))
    return Path(s).expanduser()


def _read_yaml(p: Path) -> dict:
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def read_keep(p: Path) -> tuple[str, str]:
    """Text with \\n line ends + a format tag (line ending, BOM), so rewriting a
    file on Windows keeps CRLF/LF and a UTF-8 BOM exactly as they were."""
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), ("bom" if bom else "") + nl


def write_keep(p: Path, text: str, fmt: str = "\n") -> None:
    nl = fmt.replace("bom", "") or "\n"
    data = text.replace("\r\n", "\n").replace("\n", nl).encode("utf-8")
    p.write_bytes((b"\xef\xbb\xbf" if fmt.startswith("bom") else b"") + data)
