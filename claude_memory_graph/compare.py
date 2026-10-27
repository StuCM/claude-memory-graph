"""Does the graph earn its keep? Your real questions, checked against the
graph and against Claude Code's built-in memory.

`claude-memory-graph compare questions.toml` reads questions you actually
ask (see docs/COMPARE.md for the format) and, for each, checks whether the
words a right answer needs appear in what each memory would give Claude:

- graph, unprompted: what the gate injects with the prompt, as in a session;
- graph, when Claude looks: memory_search's top hits, plus a depth-2
  recall of the first — what Claude reads if it goes to memory itself;
- built-in, at start: the project's auto memory index (MEMORY.md, first
  200 lines / 25KB: what Claude Code loads into every session), plus any
  CLAUDE.md under `path`;
- built-in, if opened: every auto memory topic file for the project, which
  Claude can open during the session;
- claude.ai: can't be checked from here — the report leaves a column for
  you to fill in after asking it.

"Contains the expected words" is a floor, not a grade: it shows whether the
knowledge is reachable at all, not whether the answer would be good. Read
the report's evidence lines before trusting a tick.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

INDEX_LINES, INDEX_BYTES = 200, 25_000


@dataclass
class Question:
    text: str
    project: str
    expect: list[str]
    path: str = ""
    note: str = ""


@dataclass
class Row:
    question: Question
    results: dict = field(default_factory=dict)    # column -> (found, total, evidence)


def load(path: Path) -> list[Question]:
    data = tomllib.loads(path.read_text())
    questions = []
    for item in data.get("question", []):
        expect = item.get("expect", [])
        if isinstance(expect, str):
            expect = [e.strip() for e in expect.split(",")]
        questions.append(Question(text=item["text"], project=item.get("project", ""),
                                  expect=[e for e in expect if e], path=item.get("path", ""),
                                  note=item.get("note", "")))
    if not questions:
        raise ValueError(f"no [[question]] entries in {path}")
    return questions


def _score(text: str, expect: list[str]) -> tuple[int, int, str]:
    low = text.lower()
    found = [e for e in expect if e.lower() in low]
    evidence = ""
    if found:
        i = low.find(found[0].lower())
        evidence = " ".join(text[max(0, i - 60): i + 80].split())
    return len(found), len(expect), evidence


# ------------------------------------------------------------------ graph

def graph_unprompted(q: Question) -> str:
    from .gate.recall import RecallExtension
    from .hookcore import HookContext
    ctx = HookContext(event="UserPromptSubmit",
                      payload={"prompt": q.text, "cwd": f"/compare/{q.project}"},
                      core={"project": q.project, "session_id": "compare"}, state={})
    return RecallExtension().on_user_prompt_submit(ctx) or ""


def graph_on_request(q: Question, store) -> str:
    from .tools import search
    from .tools.recall import handle as recall
    found = search.handle(store, q.text, limit=5)
    text = found
    first = next((line for line in found.splitlines() if line.startswith("- ")), "")
    if "'" in first:
        model = first[2:].split(" ", 1)[0]
        name = first.split("'", 2)[1]
        try:
            text += "\n" + recall(store, model, name, depth=2)
        except Exception:  # noqa: BLE001 — a recall failure is just no extra text
            pass
    return text


# --------------------------------------------------------------- built-in

def _project_dirs(q: Question, home: Path) -> list[Path]:
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return []
    if q.path:
        exact = root / str(Path(q.path).expanduser().resolve()).replace("/", "-")
        if exact.is_dir():
            return [exact]
    suffix = f"-{q.project}" if q.project else None
    return sorted(d for d in root.iterdir() if d.is_dir() and suffix and d.name.endswith(suffix))


def builtin_at_start(q: Question, home: Path) -> str:
    parts = []
    for d in _project_dirs(q, home):
        index = d / "memory" / "MEMORY.md"
        if index.exists():
            text = "\n".join(index.read_text(errors="ignore").splitlines()[:INDEX_LINES])
            parts.append(text[:INDEX_BYTES])
    if q.path:
        repo = Path(q.path).expanduser()
        for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
            if (repo / name).exists():
                parts.append((repo / name).read_text(errors="ignore"))
    user = home / ".claude" / "CLAUDE.md"
    if user.exists():
        parts.append(user.read_text(errors="ignore"))
    return "\n".join(parts)


def builtin_if_opened(q: Question, home: Path) -> str:
    parts = []
    for d in _project_dirs(q, home):
        for f in sorted((d / "memory").glob("*.md")):
            parts.append(f.read_text(errors="ignore"))
    return "\n".join(parts)


# ------------------------------------------------------------------ run

COLUMNS = [("graph_unprompted", "Graph, unprompted"),
           ("graph_on_request", "Graph, when Claude looks"),
           ("builtin_at_start", "Built-in, at start"),
           ("builtin_if_opened", "Built-in, if opened")]


def run(questions: list[Question], store, home: Path | None = None) -> list[Row]:
    home = home or Path.home()
    rows = []
    for q in questions:
        texts = {"graph_unprompted": graph_unprompted(q),
                 "graph_on_request": graph_on_request(q, store),
                 "builtin_at_start": builtin_at_start(q, home),
                 "builtin_if_opened": builtin_if_opened(q, home)}
        rows.append(Row(q, {k: _score(v, q.expect) for k, v in texts.items()}))
    return rows


def _cell(result) -> str:
    found, total, _ = result
    if total == 0:
        return "?"
    return "✓" if found == total else (f"{found}/{total}" if found else "✗")


def report(rows: list[Row], source: str) -> str:
    lines = ["# Memory comparison", "",
             f"Questions: `{source}` · run {__import__('datetime').date.today()}", "",
             "✓ every expected word is there · n/m some · ✗ none. A tick means the knowledge "
             "is *reachable*, not that the answer would be good — check the evidence below.", "",
             "| # | Question | " + " | ".join(label for _, label in COLUMNS) + " | claude.ai (fill in) |",
             "|---|---|" + "---|" * len(COLUMNS) + "---|"]
    for i, row in enumerate(rows, 1):
        cells = " | ".join(_cell(row.results[k]) for k, _ in COLUMNS)
        lines.append(f"| {i} | {row.question.text} | {cells} |  |")
    totals = {k: sum(1 for r in rows if _cell(r.results[k]) == "✓") for k, _ in COLUMNS}
    lines += ["", "**Fully answered:** " + " · ".join(
        f"{label} {totals[k]}/{len(rows)}" for k, label in COLUMNS), ""]
    graph_only = [i for i, r in enumerate(rows, 1)
                  if max(_cell(r.results[k]) == "✓" for k in ("graph_unprompted", "graph_on_request"))
                  and not max(_cell(r.results[k]) == "✓" for k in ("builtin_at_start",
                                                                   "builtin_if_opened"))]
    builtin_only = [i for i, r in enumerate(rows, 1)
                    if not max(_cell(r.results[k]) == "✓" for k in ("graph_unprompted",
                                                                    "graph_on_request"))
                    and max(_cell(r.results[k]) == "✓" for k in ("builtin_at_start",
                                                                 "builtin_if_opened"))]
    lines += [f"**Only the graph:** {', '.join(map(str, graph_only)) or 'none'} · "
              f"**only built-in:** {', '.join(map(str, builtin_only)) or 'none'}", "",
              "## Evidence", ""]
    for i, row in enumerate(rows, 1):
        q = row.question
        lines.append(f"### {i}. {q.text}")
        lines.append(f"project `{q.project or '—'}` · expects: {', '.join(q.expect) or '—'}"
                     + (f" · {q.note}" if q.note else ""))
        for k, label in COLUMNS:
            found, total, evidence = row.results[k]
            lines.append(f"- **{label}** {found}/{total}" + (f": …{evidence}…" if evidence else ""))
        lines.append("")
    return "\n".join(lines)


def main(path: Path, out: Path | None) -> None:
    import tempfile

    from . import remote
    from .gate.runtime import store_dir
    from .hookcore.state import STATE_HOME_ENV
    from .store import MemoryStore

    questions = load(path)
    folder = remote.fetch_replica(force=True) if remote.server_config() else None
    folder = folder or store_dir()
    # The gate writes telemetry (injections.jsonl) and a session memo; a
    # comparison run must not land in the real logs the miss detector reads.
    saved = {k: os.environ.get(k) for k in ("MEMORY_GRAPH_PATH", STATE_HOME_ENV)}
    with tempfile.TemporaryDirectory(prefix="mg-compare-") as scratch:
        os.environ["MEMORY_GRAPH_PATH"] = str(folder)
        os.environ[STATE_HOME_ENV] = scratch
        try:
            store = MemoryStore.open_or_create(folder)
            text = report(run(questions, store), str(path))
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    out = out or path.with_name(path.stem + "-report.md")
    out.write_text(text)
    print(text.split("## Evidence")[0].rstrip())
    print(f"\nFull report with evidence: {out}")
    if remote.server_config():
        print("(server mode: the graph checked is a fresh copy of the server's)")
