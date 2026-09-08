"""Doctor — one command, one verdict: why isn't memory doing anything?

Three wiring issues have bitten in practice, and every one of them looks
identical from the user's seat ("nothing traverses / nothing records"):
  1. stale plugin — the hooks that inject and record aren't registered;
  2. path mismatch — the CLI reads a different store/home than the plugin
     writes, so healthy activity looks like silence;
  3. empty or orphaned graph — capture never reached it, or nodes landed
     with no links so there is nothing to traverse.

Doctor checks all of them from the shared artefacts (logs, store, context
dir) that every install writes regardless of which process wrote them,
PRINTS the paths it inspected (so a mismatch is obvious at a glance), and
ends with a single prioritised diagnosis. Read-only, fail-open.
"""

import os
import time
from pathlib import Path

from claude_hook_kit import state_home

from .pulse import _read_jsonl, _graph_counts
from .runtime import store_dir


def _ctx_dir() -> Path:
    env = os.environ.get("CLAUDE_CONTEXT_DIR")
    return Path(env) if env else Path.home() / ".claude" / "context"


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("claude-memory-graph")
    except Exception:
        return "?"


def _age(entries: list[dict]) -> str:
    ts = [e.get("ts", 0) for e in entries if e.get("ts")]
    if not ts:
        return "never"
    delta = time.time() - max(ts)
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    return f"{int(delta / 86400)}d ago"


def report() -> str:
    L = []                 # transcript lines
    findings = []          # (severity, message, fix)

    def line(s=""):
        L.append(s)

    line(f"claude-memory-graph doctor · v{_version()}")
    line()

    # -- paths (mismatch is the silent killer; show them) ------------------
    store_p = store_dir()
    home_p = state_home()
    ctx_p = _ctx_dir()
    line("Paths inspected (must match what the plugin uses):")
    line(f"  store       {store_p}"
         + ("" if store_p.exists() else "   ⚠ MISSING"))
    line(f"  logs (home) {home_p}"
         + ("" if home_p.exists() else "   ⚠ MISSING"))
    line(f"  context     {ctx_p}"
         + ("" if ctx_p.exists() else "   ⚠ MISSING"))
    for name, val in (("MEMORY_GRAPH_PATH", os.environ.get("MEMORY_GRAPH_PATH")),
                      ("CLAUDE_HOOK_KIT_HOME", os.environ.get("CLAUDE_HOOK_KIT_HOME")),
                      ("CLAUDE_CONTEXT_DIR", os.environ.get("CLAUDE_CONTEXT_DIR"))):
        if val:
            line(f"  env {name}={val}")
            findings.append(("info",
                f"{name} is set in this shell — the plugin MUST run with the same "
                f"value, or the CLI and the hooks look at different data.",
                f"Confirm the plugin's env matches, or unset {name} here."))
    line()

    # -- logs: are hooks firing? -------------------------------------------
    inj = _read_jsonl("injections.jsonl", 0)
    cap = _read_jsonl("capture.jsonl", 0)
    rec = _read_jsonl("explicit-recalls.jsonl", 0)
    fired = [e for e in inj if e.get("fired") and "kind" not in e]
    blocks = [e for e in cap if e.get("kind") == "block"]
    writes = [e for e in cap if e.get("kind") == "write"]
    digs = [e for e in blocks if e.get("dig")]
    distills = [e for e in cap if e.get("kind") == "distill"]
    line("Hook activity (written by the plugin's hooks — empty means they never ran):")
    line(f"  prompt decisions : {len(inj):>4}   last {_age(inj)}")
    line(f"  graph injections : {len(fired):>4}")
    line(f"  stop blocks      : {len(blocks):>4}   ({len(digs)} from digs)   last {_age(blocks)}")
    line(f"  context writes   : {len(writes):>4}   last {_age(writes)}")
    line(f"  auto-distill runs: {len(distills):>4}   last {_age(distills)}")
    line(f"  explicit recalls : {len(rec):>4}")
    line()

    hooks_dead = not inj and not cap
    if hooks_dead:
        findings.append(("FAIL",
            "No hook activity has EVER been logged — the plugin's hooks are not firing.",
            "Update the plugin (claude plugin update memory-graph) and start a FRESH "
            "session; hooks load at session start. Check /hooks lists Stop + PostToolUse."))
    elif not blocks:
        findings.append(("WARN",
            "Prompts are logged but no Stop blocks ever fired — the capture/dig lane "
            "isn't wired (older plugin), or the diary was never behind.",
            "Confirm plugin >= 0.8 and that /hooks lists Stop and a PostToolUse "
            "(Grep|Glob|Read|Bash) matcher."))
    elif digs and not writes:
        findings.append(("WARN",
            "Dig blocks fire but no context writes are observed — the model is being "
            "asked for trace entries after greps but not writing them.",
            "The block names the file; if it's ignored repeatedly, the context dir may "
            "be wrong (see paths above) or the model is deprioritising it."))

    # -- graph: is there anything to traverse? -----------------------------
    nodes, links = _graph_counts()
    orphans = -1
    try:
        from ..store import MemoryStore
        from .. import gaps as gaps_mod
        g = gaps_mod.analyse(MemoryStore.open_or_create(store_p), limit=1)
        orphans = len(g.orphans)
    except Exception:
        pass
    line("Graph:")
    if nodes < 0:
        line("  could not open the store")
    else:
        line(f"  nodes {nodes}   links {links}"
             + (f"   orphans (no links) {orphans}" if orphans >= 0 else ""))
    line()
    if nodes == 0:
        findings.append(("FAIL",
            "The graph is EMPTY — nothing to recall or traverse.",
            "If hooks are dead (above), fix that first. Otherwise the diary hasn't "
            "distilled: check for context files, then run the memory_distill tool in a "
            "session (auto-distill also runs at each server start)."))
    elif nodes > 0 and links == 0:
        findings.append(("WARN",
            "Nodes exist but NONE are linked — there is nothing to traverse. The model "
            "is writing plain notes, not structured `key: value` entries with links.",
            "Run /memory-graph:reflect to add links now; nudge structured-entry use so "
            "future distills carry `affects:`/`concepts:`/`manifestsIn:` lines."))
    elif orphans > 0 and orphans >= nodes / 2:
        findings.append(("WARN",
            f"{orphans}/{nodes} nodes have no links — half the graph is unreachable by "
            "traversal.",
            "claude-memory-graph gaps, then /memory-graph:reflect to connect them."))

    # -- context backlog ---------------------------------------------------
    try:
        from ..context_entries import undistilled_files
        undistilled = undistilled_files(ctx_p)
        line(f"Context files: {len(list(ctx_p.glob('*.md')))} total, "
             f"{len(undistilled)} undistilled")
    except Exception:
        pass
    line()

    # -- note about the code graph (a recurring expectation gap) -----------
    line("Note: there is no derived CODE graph (horizon feature). A grep-heavy turn "
         "produces a TRACE entry in the context file → a Pattern(kind: trace) node after "
         "distill. Look for those with:  claude-memory-graph reflect")
    line()

    # -- verdict -----------------------------------------------------------
    order = {"FAIL": 0, "WARN": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f[0], 3))
    line("── Diagnosis ─────────────────────────────────────────────")
    if not [f for f in findings if f[0] in ("FAIL", "WARN")]:
        line("Everything looks wired and populated. If recall still feels quiet, use "
             "`claude-memory-graph gate \"<prompt>\"` to see the exact scoring, and "
             "`misses` to catch false negatives.")
    for sev, msg, fix in findings:
        tag = {"FAIL": "✗ FAIL", "WARN": "! WARN", "info": "· note"}[sev]
        line(f"{tag}  {msg}")
        line(f"        → {fix}")
    return "\n".join(L)
