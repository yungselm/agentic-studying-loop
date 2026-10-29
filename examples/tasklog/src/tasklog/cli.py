"""Command line: `tasklog add`, `tasklog done`, `tasklog list` (uses typer)."""
from pathlib import Path

import typer

from tasklog.store import Store, Task

app = typer.Typer()
STORE = Store(Path.home() / ".tasklog.json")


@app.command()
def add(title: str, tag: list[str] = typer.Option([], "--tag", "-t")) -> None:
    tasks = STORE.load()
    tasks.append(Task(title, tags=tag))
    STORE.save(tasks)
    typer.echo(f"added #{len(tasks)}: {title}")


@app.command("list")
def list_tasks(open_only: bool = False) -> None:
    for i, t in enumerate(STORE.load(), start=1):
        if open_only and t.done:
            continue
        typer.echo(f"{i:>3} [{'x' if t.done else ' '}] {t.title}")


if __name__ == "__main__":
    app()
