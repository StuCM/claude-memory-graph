"""Session-context corpus: the log, indexed for per-prompt recall.

The context files become the PRIMARY per-prompt retrieval source (the
graph is the second layer): parse undistilled entries with the shared
parser and hand them to the gate's scorer as docs.

Eligibility — the duplication rule (docs/tasks/session-context-recall.md):
an entry is only injectable when its authoring context is GONE.
- Files untouched since before this session started belong to OTHER
  sessions: always eligible (the handoff case).
- Files written during THIS session hold entries the model still has in
  its live conversation — eligible only after a compaction has erased
  that conversation (core.events["PreCompact"] > 0).

File-level granularity is deliberate for v1; the index is derived and
disposable, rebuilt per prompt from the files (dozens of entries — the
scan is noise next to the graph scan).
"""

from datetime import datetime, timezone
from pathlib import Path

from claude_hook_kit import terms_pos

from ..context_entries import undistilled_files, parse_file


def _context_dir() -> Path:
    import os
    env = os.environ.get("CLAUDE_CONTEXT_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "context"


def _session_epoch(started_at: str) -> float:
    """core.started_at ('%Y-%m-%dT%H:%M:%SZ', UTC) -> epoch; 0 on failure
    (fail open = treat every file as another session's)."""
    try:
        return datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except (ValueError, TypeError):
        return 0.0


def docs(project: str, started_at: str, precompact_count: int,
         bigrams_fn) -> list[dict]:
    """Eligible log entries as scoring docs (same shape the gate scores)."""
    session_start = _session_epoch(started_at)
    out: list[dict] = []
    for path in undistilled_files(_context_dir(), project):
        try:
            own_session = path.stat().st_mtime >= session_start > 0
        except OSError:
            continue
        if own_session and precompact_count == 0:
            continue  # its content is still in the live conversation
        _, entries = parse_file(path)
        for e in entries:
            name_pos = terms_pos(e.name)
            all_pos = terms_pos(e.text)
            if not all_pos:
                continue
            out.append({
                "gid": None,
                "iri": f"log:{e.source}:{e.line}",
                "key": f"{e.source}:{e.type}:{e.name}",
                "name": e.name,
                "model": e.type,
                "desc": "; ".join(f"{k}: {v}" for k, v in e.properties.items())[:300],
                "source_file": e.source,
                "name_terms": {w for _, w in name_pos},
                "terms": {w for _, w in all_pos},
                "name_bigrams": bigrams_fn(name_pos),
                "bigrams": bigrams_fn(all_pos),
            })
    return out
