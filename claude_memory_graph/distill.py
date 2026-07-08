"""Mechanical distill — the no-LLM lane (structured-context-entries phase 2).

Structured context entries already carry the graph shape, so promoting
them is parsing, not reasoning: parse → fold (latest values win) → apply
through the same handlers the MCP tools use, with the hard capture rules
enforced unchanged. Anything the mechanical lane can't safely handle —
narrative bullets, duplicate-guard hits, unknown relations, missing
required properties — lands in the RESIDUE, reported for the /distill
skill's (now small) LLM pass. Quality is preserved by refusing, never by
forcing.

Run it between sessions: `claude-memory-graph distill` (the MCP server
holds the graph in memory and saves after each mutation, so a CLI write
during a live session would be overwritten by the session's next save —
same constraint as every terminal write).
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .context_entries import Entry, fold, parse_file, undistilled_files
from .store import MemoryStore
from .tools.store_resource import handle_resource
from .tools.link import handle_link


def context_dir() -> Path:
    env = os.environ.get("CLAUDE_CONTEXT_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "context"


@dataclass
class Report:
    files: list = field(default_factory=list)
    stored: list = field(default_factory=list)     # "Model 'name'" applied
    linked: int = 0
    residue: list = field(default_factory=list)    # (entry, reason) for the LLM lane
    archived: list = field(default_factory=list)

    def render(self) -> str:
        lines = [f"files: {len(self.files)} · nodes: {len(self.stored)} · "
                 f"links: {self.linked} · residue: {len(self.residue)} · "
                 f"archived: {len(self.archived)}"]
        for msg in self.stored:
            lines.append(f"  {msg}")
        if self.residue:
            lines.append("residue (needs the /memory-graph:distill skill):")
            for entry, reason in self.residue:
                lines.append(f"  {entry.source}:{entry.line} "
                             f"[{entry.type}: {entry.name[:60]}] — {reason}")
        return "\n".join(lines)


def _apply_entry(store: MemoryStore, entry: Entry, report: Report) -> bool:
    """One folded entry → node + concepts + links. Refuses (to residue)
    rather than forcing; returns True when the node was applied."""
    properties = {"name": entry.name, **entry.properties,
                  "sourceContext": entry.source}
    try:
        msg = handle_resource(store, entry.type, properties, force=False)
    except ValueError as exc:
        report.residue.append((entry, str(exc)))
        return False
    report.stored.append(msg)

    for label in entry.concepts:
        try:
            store.store_concept("Concept", label, {})
            handle_link(store, entry.type, entry.name, "Concept", label,
                        "hasConcept", {})
            report.linked += 1
        except ValueError as exc:
            report.residue.append((entry, f"concept '{label}': {exc}"))

    for relation, model, name in entry.links:
        try:
            handle_link(store, entry.type, entry.name, model, name, relation, {})
            report.linked += 1
        except ValueError as exc:
            # unknown relation / missing target — the skill lane decides
            report.residue.append(
                (entry, f"link {relation} -> {model}/{name}: {exc}"))
    return True


def _mark_distilled(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(
        re.sub(r"^distilled:\s*false$", "distilled: true", text,
               count=1, flags=re.MULTILINE),
        encoding="utf-8")


def _archive(path: Path) -> Path:
    archive = path.parent / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / path.name
    if target.exists():  # never overwrite an archived file
        target = archive / f"{path.stem}__{datetime.now().strftime('%H%M%S')}{path.suffix}"
    path.rename(target)
    return target


def distill(store: MemoryStore, directory: Path | None = None,
            project: str | None = None, dry_run: bool = False,
            keep: bool = False) -> Report:
    """The mechanical lane. Narrative entries and refused promotions land in
    the residue; a file is only marked distilled + archived when NOTHING in
    it was left behind (a file with residue stays active for the skill)."""
    directory = directory or context_dir()
    report = Report()
    for path in undistilled_files(directory, project):
        _, entries = parse_file(path)
        report.files.append(path.name)
        residue_before = len(report.residue)

        promotable = [e for e in entries if e.promotable]
        for entry in fold(promotable).values():
            if dry_run:
                report.stored.append(f"[dry-run] {entry.type} '{entry.name}'")
                continue
            _apply_entry(store, entry, report)

        for entry in entries:
            if not entry.promotable and entry.structured:
                report.residue.append(
                    (entry, f"head type '{entry.type}' is not a graph model"))
            elif not entry.structured:
                report.residue.append((entry, "narrative entry (LLM lane)"))

        clean = len(report.residue) == residue_before
        if not dry_run and clean and not keep:
            _mark_distilled(path)
            report.archived.append(_archive(path).name)
    if not dry_run and report.stored:
        store.save()
    return report
