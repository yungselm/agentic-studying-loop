"""Persistence: load/save the task list as JSON, written atomically."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Task:
    title: str
    done: bool = False
    tags: list[str] = field(default_factory=list)


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Task]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Task(**item) for item in raw]

    def save(self, tasks: list[Task]) -> None:
        data = json.dumps([asdict(t) for t in tasks], indent=2)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, self.path)
