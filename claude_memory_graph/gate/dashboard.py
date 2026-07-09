"""Dashboard — a self-contained HTML report generated from the logs.

The occasional-check surface the operator asked for: everything pulse
knows, laid out visually with a per-day activity strip, plus the graph's
health (gaps) and the miss report's headline. Mechanically generated —
no server, no dependencies; open the file in a browser.

`claude-memory-graph dashboard [--days N] [--out FILE]`
"""

import html
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from claude_hook_kit import state_home

from . import misses as misses_mod
from .pulse import _graph_counts, _read_jsonl


def _day(ts: float) -> str:
    return time.strftime("%d %b", time.localtime(ts))


def _bars(days: list[str], series: dict[str, int], color: str, label: str) -> str:
    peak = max([series.get(d, 0) for d in days] + [1])
    bars = "".join(
        f'<div class="bar" title="{d}: {series.get(d, 0)} {label}">'
        f'<i style="height:{max(4, round(46 * series.get(d, 0) / peak))}px;'
        f'background:{color}"></i><span>{d.split()[0]}</span></div>'
        for d in days
    )
    return f'<div class="strip">{bars}</div>'


def build(days: int = 14) -> str:
    cutoff = time.time() - days * 86400
    injections = _read_jsonl("injections.jsonl", cutoff)
    recalls = _read_jsonl("explicit-recalls.jsonl", cutoff)
    capture = _read_jsonl("capture.jsonl", cutoff)

    graph_lines = [e for e in injections if "kind" not in e]
    fired = [e for e in graph_lines if e.get("fired")]
    log_fired = [e for e in injections if e.get("kind") == "log" and e.get("fired")]
    primes = [e for e in injections if e.get("kind") == "prime"]
    blocks = [e for e in capture if e.get("kind") == "block"]
    writes = [e for e in capture if e.get("kind") == "write"]
    distills = [e for e in capture if e.get("kind") == "distill"]
    sessions = {e.get("session") for e in injections + recalls + capture} - {None, ""}
    found = sum(1 for e in recalls if e.get("found"))
    top = Counter(n for e in fired for n in e.get("nodes", [])).most_common(6)

    day_axis, per_day_prompts, per_day_paid = [], defaultdict(int), defaultdict(int)
    for offset in range(days - 1, -1, -1):
        day_axis.append(_day(time.time() - offset * 86400))
    for e in graph_lines:
        per_day_prompts[_day(e.get("ts", 0))] += 1
    for e in fired + log_fired + primes:
        per_day_paid[_day(e.get("ts", 0))] += 1

    miss_result = misses_mod.analyse()
    n_miss, n_gap = len(miss_result["misses"]), len(miss_result["gaps"])
    nodes, links = _graph_counts()

    gaps_line = ""
    try:
        from ..store import MemoryStore
        from .. import gaps as gaps_mod
        from .runtime import store_dir
        g = gaps_mod.analyse(MemoryStore.open_or_create(store_dir()), limit=5)
        gaps_line = (f"{len(g.orphans)} orphan(s) · {len(g.conceptless)} without a "
                     f"concept link · {len(g.suggestions)} suggested pair(s)")
        gap_items = "".join(
            f"<li>{html.escape(a['model'])} '{html.escape(a['name'])}' ↔ "
            f"{html.escape(b['model'])} '{html.escape(b['name'])}' "
            f"<span class=m>({html.escape(', '.join(shared[:4]))})</span></li>"
            for _, a, b, shared in g.suggestions[:5])
    except Exception:
        gap_items = ""

    try:
        from ..distill import context_dir
        from ..context_entries import undistilled_files
        backlog = len(undistilled_files(context_dir()))
    except Exception:
        backlog = 0

    def tile(value, label, note=""):
        return (f'<div class="tile"><b>{value}</b><span>{label}</span>'
                + (f'<em>{note}</em>' if note else "") + "</div>")

    payout = len(fired) + len(log_fired) + len(primes)
    rate = f"{round(100 * len(fired) / len(graph_lines))}%" if graph_lines else "—"
    last_distill = (f"last: {distills[-1].get('stored', 0)} nodes, "
                    f"{distills[-1].get('residue', 0)} residue" if distills else "no runs yet")

    top_items = "".join(f"<li>{html.escape(n)} <span class=m>×{c}</span></li>"
                        for n, c in top) or "<li class=m>nothing injected yet</li>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>memory pulse — dashboard</title>
<style>
  :root {{ --bg:#F7F8F6; --ink:#202623; --mut:#5C6862; --line:#D9DED9; --card:#fff;
          --mech:#17635A; --llm:#B4640F; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#14181A; --ink:#E6EBE7; --mut:#93A099; --line:#2C3436; --card:#1B2124;
            --mech:#53B5A6; --llm:#DE9B4E; }} }}
  body {{ margin:0; padding:2rem clamp(1rem,4vw,3rem); background:var(--bg); color:var(--ink);
         font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif; }}
  h1 {{ font-size:1.4rem; margin:0 0 .2rem; }} .m {{ color:var(--mut); }}
  .sub {{ color:var(--mut); margin-bottom:1.6rem; font-size:.9em; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
           gap:.8rem; margin-bottom:1.6rem; }}
  .tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:.9rem 1rem; display:flex; flex-direction:column; gap:.15rem; }}
  .tile b {{ font-size:1.5rem; font-variant-numeric:tabular-nums; }}
  .tile span {{ color:var(--mut); font-size:.8em; }} .tile em {{ color:var(--mut); font-size:.72em; font-style:normal; }}
  .row {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:.8rem; }}
  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; }}
  .panel h2 {{ font-size:.8rem; letter-spacing:.08em; text-transform:uppercase;
              color:var(--mut); margin:0 0 .7rem; }}
  ul {{ margin:0; padding-left:1.1rem; }} li {{ margin:.3rem 0; font-size:.92em; }}
  .strip {{ display:flex; gap:3px; align-items:flex-end; height:70px; overflow-x:auto; }}
  .bar {{ display:flex; flex-direction:column; align-items:center; gap:2px; flex:1 0 14px; }}
  .bar i {{ width:100%; border-radius:2px 2px 0 0; display:block; }}
  .bar span {{ font-size:.55rem; color:var(--mut); }}
  code {{ font-family:ui-monospace,Menlo,monospace; font-size:.88em; }}
</style></head><body>
<h1>memory pulse</h1>
<div class="sub">last {days} days · generated {time.strftime('%Y-%m-%d %H:%M')} · regenerate with <code>claude-memory-graph dashboard</code></div>
<div class="tiles">
  {tile(len(sessions), "sessions seen")}
  {tile(payout, "memory payouts", "primes + graph + log injections")}
  {tile(rate, "graph injection rate", f"{len(fired)}/{len(graph_lines)} gated prompts")}
  {tile(f"{len(blocks)} / {len(writes)}", "stop blocks / writes observed")}
  {tile(len(distills), "auto-distill runs", last_distill)}
  {tile(f"{nodes if nodes >= 0 else '—'}", "graph nodes", f"{links if links >= 0 else '—'} links")}
  {tile(n_miss, "retrieval misses", "claude-memory-graph misses")}
  {tile(backlog, "undistilled files", "residue awaits /distill" if backlog else "all promoted")}
</div>
<div class="row">
  <div class="panel"><h2>Prompts gated per day</h2>{_bars(day_axis, per_day_prompts, "var(--line)", "prompts")}</div>
  <div class="panel"><h2>Memory payouts per day</h2>{_bars(day_axis, per_day_paid, "var(--mech)", "payouts")}</div>
</div>
<div class="row" style="margin-top:.8rem">
  <div class="panel"><h2>Most-injected memories</h2><ul>{top_items}</ul></div>
  <div class="panel"><h2>Link gaps {('— ' + gaps_line) if gaps_line else ''}</h2>
    <ul>{gap_items or '<li class=m>none suggested</li>'}</ul>
    <p class="m" style="font-size:.85em">judge with <code>/memory-graph:reflect</code></p></div>
  <div class="panel"><h2>Health notes</h2><ul>
    <li>{'explicit recalls: ' + str(len(recalls)) + ' (' + str(found) + ' found)'}</li>
    <li>{str(n_gap)} capture gap(s) — wanted from memory, never stored</li>
    <li>{'⚠ blocks fire but no writes observed' if blocks and not writes else 'capture loop healthy' if writes else 'no capture activity yet'}</li>
  </ul></div>
</div>
</body></html>"""


def write(out: Path | None = None, days: int = 14) -> Path:
    path = out or (state_home() / "dashboard.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(days), encoding="utf-8")
    return path
