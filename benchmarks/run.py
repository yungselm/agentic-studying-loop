"""Run the card benchmark: each task in each setup (model × effort), with and without the workflow.

    python benchmarks/run.py --check                         # auth + isolation, costs ~nothing
    python benchmarks/run.py --task rust-ch04 --dry-run      # prepare the folders, print the plan
    python benchmarks/run.py --task rust-ch04                # the pilot: 10 runs
    python benchmarks/run.py --batch full --repeat 2 --parallel 2

Each run gets a fresh folder outside the repo and its own empty Claude Code config, so your
memory, CLAUDE.md, hooks, plugins and settings stay out. Auth: your plan through a token from
`claude setup-token` (env `CLAUDE_CODE_OAUTH_TOKEN`, or the file ~/.claude_bench_token), or
`--auth api` with `ANTHROPIC_API_KEY`.

Committed: benchmarks/results/<batch>/runs.jsonl, one line per run with tokens, cost and card
counts (no card text). Local: the run folders (cards, transcript) under --work.
Runs already in runs.jsonl are skipped, so a batch can be run in parts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
ASL = REPO / ".venv" / "bin" / "asl"
DEFAULT_WORK = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "asl-bench"
AGENT_BIN: Path | None = None    # the asl the agent sees: a plain install, not this checkout

PROMPT_WORKFLOW = """\
I'm studying {what}. It's the topic "{topic}" in my card home (`Anki cards/`); its brief in \
Overview.md is settled. Make the cards for the whole chapter in this session: all its parts, \
no need to stop between them. Don't ask me questions: decide yourself, and tell me at the end \
what you made."""

PROMPT_PLAIN = """\
I'm studying {what}; the text is in `{file}`. I want to learn it with Anki. My goal: {goal}; I \
already know {builds_on}. Write Anki cards for the whole chapter into `cards.tsv` (one card per \
line: front, a tab, back; HTML allowed) so I can import it in Anki. Don't ask me questions: \
decide yourself, and tell me at the end what you made."""


# --- setup ---------------------------------------------------------------------------------------

def load_tasks() -> dict:
    cfg = yaml.safe_load((BENCH / "tasks.yaml").read_text(encoding="utf-8"))
    local = BENCH / "tasks.local.yaml"
    if local.exists():
        extra = yaml.safe_load(local.read_text(encoding="utf-8")) or {}
        cfg["tasks"].update(extra.get("tasks") or {})
    return cfg


def _asl(*args: str, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run([str(ASL), *args], cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def prepare(run_dir: Path, config_dir: Path, task: dict, arm: str) -> str:
    """Fill a fresh run folder for one arm; returns the prompt."""
    for d in (run_dir, config_dir):
        if d.exists():
            shutil.rmtree(d)
    config_dir.mkdir(parents=True)
    src = Path(task["source"])
    src = src if src.is_absolute() else BENCH / src
    if not src.exists():
        raise SystemExit(f"missing source {src} (see the task's comment in tasks.yaml)")
    dest = run_dir / task["file"]
    dest.parent.mkdir(parents=True)
    shutil.copy2(src, dest)
    if arm == "plain":
        return PROMPT_PLAIN.format(**task)
    home = "Anki cards"
    pack = ["--pack", task["pack"]] if task.get("pack") else []
    for args in (["init-home", home, "--vault", ".", *pack],
                 ["topic", task["topic"], "--home", home, "--sources", task["file"], "--no-notes",
                  *pack, "--goal", task["goal"], "--builds-on", task["builds_on"]],
                 ["install-skills", str(config_dir / "skills")]):
        r = _asl(*args, cwd=run_dir)
        if r.returncode:
            raise SystemExit(f"asl {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    if "code_share" in task:
        ov = deck_dir(run_dir) / "Overview.md"
        text = re.sub(r"^cards: \{code: [0-9.]+\}", f"cards: {{code: {task['code_share']}}}",
                      ov.read_text(encoding="utf-8"), count=1, flags=re.M)
        ov.write_text(text, encoding="utf-8")
    return PROMPT_WORKFLOW.format(**task)


def deck_dir(run_dir: Path) -> Path:
    return next(p.parent for p in (run_dir / "Anki cards").glob("*/deck.yaml"))


def run_env(config_dir: Path, arm: str, auth: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "ANTHROPIC")) or k == "ANTHROPIC_API_KEY"}
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    if auth == "plan":
        env.pop("ANTHROPIC_API_KEY", None)           # never bill the API by accident
        env["CLAUDE_CODE_OAUTH_TOKEN"] = plan_token()
    elif not env.get("ANTHROPIC_API_KEY"):
        raise SystemExit("--auth api needs ANTHROPIC_API_KEY")
    if arm == "workflow":
        env["PATH"] = f"{AGENT_BIN}{os.pathsep}{env.get('PATH', '')}"
    return env


def install_agent_asl(work: Path) -> Path:
    """Install this checkout (not editable) into its own venv, as `uv tool install` would.
    The agent then finds an ordinary installed `asl`, not the repo: with the repo's .venv on
    PATH, `which asl` led agents into the source code."""
    venv = work / "_asl"
    if venv.exists():
        shutil.rmtree(venv)
    for cmd in (["uv", "venv", "-q", "--python", "3.12", str(venv)],
                ["uv", "pip", "install", "-q", "--python", str(venv / "bin" / "python"),
                 f"{REPO}[python]"]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"{' '.join(cmd)} failed:\n{r.stderr}")
    return venv / "bin"


def plan_token() -> str:
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    f = Path.home() / ".claude_bench_token"
    if not tok and f.exists():
        m = re.search(r"CLAUDE_CODE_OAUTH_TOKEN=['\"]?([^'\"\s]+)", f.read_text(encoding="utf-8"))
        tok = m and m.group(1)
    if not tok:
        raise SystemExit("no token: run `claude setup-token` and save it as "
                         "`export CLAUDE_CODE_OAUTH_TOKEN=...` in ~/.claude_bench_token")
    return tok


# --- one run -------------------------------------------------------------------------------------

def claude_cmd(prompt: str, model: str, effort: str, budget: float) -> list[str]:
    return [shutil.which("claude") or "claude", "-p", prompt, "--model", model, "--effort", effort,
            "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--permission-mode", "bypassPermissions", "--max-budget-usd", str(budget)]


def run_one(spec: dict, args, meta: dict) -> dict:
    run_dir = args.work / args.batch / spec["run_id"]
    config_dir = args.work / args.batch / (spec["run_id"] + ".config")
    task = spec["task_cfg"]
    prompt = prepare(run_dir, config_dir, task, spec["arm"])
    cmd = claude_cmd(prompt, spec["model"], spec["effort"], args.max_budget)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.monotonic()
    status, error = "ok", ""
    with open(run_dir.parent / (spec["run_id"] + ".stream.jsonl"), "w", encoding="utf-8") as out:
        try:
            p = subprocess.run(cmd, cwd=run_dir, env=run_env(config_dir, spec["arm"], args.auth),
                               stdout=out, stderr=subprocess.PIPE, text=True,
                               timeout=args.timeout * 60)
            if p.returncode:
                status, error = "error", (p.stderr or "")[-500:]
        except subprocess.TimeoutExpired:
            status, error = "timeout", f"over {args.timeout} min"
    result = last_result(run_dir.parent / (spec["run_id"] + ".stream.jsonl"))
    if result.get("is_error") and status == "ok":
        status, error = "error", str(result.get("subtype") or result.get("result"))[:500]
    rec = {
        "run_id": spec["run_id"], "batch": args.batch, "task": spec["task"],
        "kind": task["kind"], "arm": spec["arm"], "setup": spec["setup"],
        "model": spec["model"], "effort": spec["effort"], "rep": spec["rep"],
        "started": started, "status": status, "error": error,
        "wall_s": round(time.monotonic() - t0),
        **usage(result),
        **(cards_workflow(run_dir) if spec["arm"] == "workflow" else cards_plain(run_dir)),
        **meta,
    }
    shutil.rmtree(config_dir, ignore_errors=True)    # holds nothing worth keeping
    return rec


def last_result(stream: Path) -> dict:
    res = {}
    if stream.exists():
        for line in stream.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "result":
                res = ev
    return res


def usage(result: dict) -> dict:
    """Tokens per kind, summed over every model the run used (side calls included)."""
    by_model = {}
    tot = Counter()
    for model, u in (result.get("modelUsage") or {}).items():
        row = {"input": u.get("inputTokens", 0), "cache_read": u.get("cacheReadInputTokens", 0),
               "cache_write": u.get("cacheCreationInputTokens", 0),
               "output": u.get("outputTokens", 0), "thinking": u.get("thinkingTokens", 0),
               "cost_usd": round(u.get("costUSD", 0.0), 4)}
        by_model[model] = row
        tot.update({k: v for k, v in row.items() if k != "cost_usd"})
    return {"tokens": dict(tot), "tokens_total": sum(v for k, v in tot.items() if k != "thinking"),
            "cost_usd": round(result.get("total_cost_usd") or 0.0, 4), "by_model": by_model,
            "turns": result.get("num_turns"), "api_s": round((result.get("duration_api_ms") or 0) / 1000)}


def cards_workflow(run_dir: Path) -> dict:
    sys.path.insert(0, str(REPO))
    from studyloop.core.cards.io import load_file
    deck = deck_dir(run_dir)
    types = Counter()
    for f in sorted(deck.glob("*.yaml")):
        if f.name != "deck.yaml" and not f.name.startswith("_"):
            try:
                types.update(c.get("type", "code") for c in load_file(f))
            except Exception as e:                    # a broken file is a result too
                types["unreadable"] += 1
                print(f"  {f.name}: {e}", file=sys.stderr)
    lint = _asl("lint", str(deck), cwd=run_dir)
    hard = [ln for ln in lint.stdout.splitlines() if ln.startswith("! [") and " -> " in ln]
    flagged = {ln.split(" -> ")[0].split("] ", 1)[1] for ln in hard}
    check = _asl("check", str(deck), cwd=run_dir, timeout=1800) if sum(types.values()) else None
    n = sum(types.values())
    return {"cards": n, "card_types": dict(types), "lint_problems": len(hard),
            "cards_flagged": len(flagged), "check_ok": None if check is None else check.returncode == 0}


def cards_plain(run_dir: Path) -> dict:
    f = run_dir / "cards.tsv"
    if not f.exists():
        return {"cards": 0, "card_types": {}}
    with open(f, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.reader(fh, delimiter="\t") if any(c.strip() for c in r)
                and not r[0].startswith("#")]
    return {"cards": len(rows), "card_types": {"basic": len(rows)}}


# --- grid ----------------------------------------------------------------------------------------

def meta_info() -> dict:
    def out(cmd):
        try:
            return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout.strip()
        except OSError:
            return ""
    h = hashlib.sha256()
    for f in sorted((REPO / "skills").rglob("*")):
        if f.is_file():
            h.update(f.relative_to(REPO).as_posix().encode() + f.read_bytes())
    return {"claude_version": out(["claude", "--version"]).split(" ")[0],
            "repo_commit": out(["git", "rev-parse", "--short", "HEAD"])
            + ("+dirty" if out(["git", "status", "--porcelain", "--", "studyloop", "skills"]) else ""),
            "skills_hash": h.hexdigest()[:12]}


def plan(cfg: dict, args) -> list[dict]:
    tasks = args.task or list(cfg["tasks"])
    setups = args.setup or list(cfg["setups"])
    arms = args.arm or cfg["arms"]
    specs = []
    for t in tasks:
        for s in setups:
            for arm in arms:
                for rep in range(1, args.repeat + 1):
                    m = cfg["setups"][s]
                    specs.append({"run_id": f"{t}__{arm}__{s}__r{rep}", "task": t,
                                  "task_cfg": cfg["tasks"][t], "setup": s, "arm": arm, "rep": rep,
                                  **m})
    random.Random(args.seed).shuffle(specs)          # no setup always runs on a warm cache
    return specs


def check(args) -> int:
    """A one-word Haiku run in a fresh config with the skills installed: proves the auth works
    and that nothing of yours (memory, CLAUDE.md, plugins) leaks in."""
    d = args.work / "_check"
    cfg = d.parent / "_check.config"
    for x in (d, cfg):
        shutil.rmtree(x, ignore_errors=True)
    d.mkdir(parents=True)
    cfg.mkdir()
    _asl("install-skills", str(cfg / "skills"), cwd=d)
    prompt = ("List, one per line: the skills you can use (names only), then any CLAUDE.md or "
              "memory content you were given (or 'none').")
    p = subprocess.run(claude_cmd(prompt, "claude-haiku-5-5", "low", 1), cwd=d,
                       env=run_env(cfg, "workflow", args.auth), capture_output=True, text=True,
                       timeout=300)
    res = {}
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            res = ev
    print(res.get("result") or p.stderr or p.stdout[-2000:])
    print(json.dumps(usage(res), indent=1) if res else "")
    shutil.rmtree(cfg, ignore_errors=True)
    return 0 if res and not res.get("is_error") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--task", action="append",
                    help="task id, repeatable (default: all in tasks.yaml + tasks.local.yaml)")
    ap.add_argument("--setup", action="append", help="setup id, repeatable (default: all)")
    ap.add_argument("--arm", action="append", choices=["workflow", "plain"])
    ap.add_argument("--repeat", type=int, default=1, help="runs per cell")
    ap.add_argument("--batch", default="pilot", help="results/<batch>/ (default: pilot)")
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--limit", type=int, help="stop after this many runs (spread a batch over days)")
    ap.add_argument("--auth", choices=["plan", "api"], default="plan")
    ap.add_argument("--max-budget", type=float, default=15.0, help="USD cap per run")
    ap.add_argument("--timeout", type=int, default=60, help="minutes per run")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--work", type=Path, default=DEFAULT_WORK, help=f"run folders (default {DEFAULT_WORK})")
    ap.add_argument("--dry-run", action="store_true", help="prepare one folder per arm, print the plan")
    ap.add_argument("--check", action="store_true", help="test auth and isolation, then stop")
    args = ap.parse_args()
    args.work = args.work.expanduser().resolve()
    if REPO in args.work.parents or args.work == REPO:
        raise SystemExit("--work must be outside the repo (the agent would see its CLAUDE.md and git)")
    if not ASL.exists():
        raise SystemExit(f"{ASL} missing: run `uv sync --all-extras` in the repo first")
    global AGENT_BIN
    if not args.dry_run:
        print("installing asl for the agent ...", flush=True)
        AGENT_BIN = install_agent_asl(args.work)
    if args.check:
        return check(args)

    cfg = load_tasks()
    out_dir = BENCH / "results" / args.batch
    runs_file = out_dir / "runs.jsonl"
    done = set()
    if runs_file.exists():
        done = {json.loads(ln)["run_id"] for ln in runs_file.read_text(encoding="utf-8").splitlines()
                if ln.strip() and json.loads(ln)["status"] == "ok"}
    specs = [s for s in plan(cfg, args) if s["run_id"] not in done]
    if args.limit:
        specs = specs[:args.limit]
    print(f"{len(specs)} run(s) to do, {len(done)} done in {runs_file.relative_to(REPO)}")
    if args.dry_run:
        for s in specs:
            print(f"  {s['run_id']}")
        for arm in {s["arm"] for s in specs}:
            s = next(x for x in specs if x["arm"] == arm)
            d = args.work / "_dry" / arm
            prompt = prepare(d, d.parent / f"{arm}.config", s["task_cfg"], arm)
            print(f"\n[{arm}] {d}\n{prompt}\n$ {' '.join(claude_cmd('<prompt>', s['model'], s['effort'], args.max_budget))}")
        return 0

    meta = meta_info()
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def one(s):
        print(f"start  {s['run_id']}", flush=True)
        try:
            rec = run_one(s, args, meta)
        except Exception as e:                        # one broken run doesn't stop the batch
            print(f"failed {s['run_id']}: {e}", flush=True)
            return None
        with lock, open(runs_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"done   {s['run_id']}: {rec['status']}, {rec['tokens_total']:,} tokens, "
              f"${rec['cost_usd']:.2f}, {rec['cards']} cards, {rec['wall_s'] // 60} min", flush=True)
        return rec

    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        list(ex.map(one, specs))
    print(f"\nsummary: python benchmarks/summary.py {args.batch}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped; run the same command again to continue (finished runs are skipped)")
        sys.exit(130)
