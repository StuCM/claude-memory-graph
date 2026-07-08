"""Parse context-file entries (hooks/context-protocol.md's format).

The write-ahead log's structured entries mirror the MCP call arguments —
a head bullet plus indented `key: value` lines — regular enough to parse
without an LLM. This module is the shared foundation for two consumers:

- **mechanical distill** (distill.py): fold entries and apply them to the
  graph with zero LLM tokens;
- **session-context recall** (gate/session_corpus.py): index entries so
  the gate can inject the relevant ones per prompt.

Narrative bullets (no continuation lines) parse too — they carry text for
retrieval but are never mechanically promoted to the graph.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .ontology import RESOURCE_MODELS, CONCEPT_TYPES

_HEAD = re.compile(r"^- \[([\d:. -]+)\]\s+([A-Z][A-Za-z ]*?):\s+(.+)$")
_CONT = re.compile(r"^ {2,}([A-Za-z][A-Za-z0-9_]*):\s+(.+)$")
_LINK_VALUE = re.compile(r"^([A-Z][A-Za-z]*)/(.+)$")
_FRONTMATTER_KEY = re.compile(r"^(\w+):\s*(.*)$")

# Head categories that are narrative-only lanes (never mechanical models);
# everything else must be a RESOURCE_MODEL to be promotable.
_KNOWN_TYPES = set(RESOURCE_MODELS) | set(CONCEPT_TYPES)


@dataclass
class Entry:
    type: str                       # head token: "Decision", "Problem", …
    name: str                       # head text after the colon
    time: str = ""                  # the [..] stamp, verbatim
    properties: dict = field(default_factory=dict)      # key -> value
    links: list = field(default_factory=list)           # (relation, model, name)
    concepts: list = field(default_factory=list)        # labels
    source: str = ""                # file name the entry came from
    line: int = 0                   # 1-based head-line number in the file

    @property
    def structured(self) -> bool:
        return bool(self.properties or self.links or self.concepts)

    @property
    def promotable(self) -> bool:
        """Mechanically promotable: structured AND head type is a graph model."""
        return self.structured and self.type in RESOURCE_MODELS

    @property
    def text(self) -> str:
        """All entry text, for retrieval indexing."""
        parts = [self.name] + list(self.properties.values())
        parts += [f"{m} {n}" for _, m, n in self.links] + self.concepts
        return " ".join(parts)


def _continuation(entry: Entry, key: str, value: str) -> None:
    if key == "concepts":
        entry.concepts.extend(c.strip() for c in value.split(",") if c.strip())
        return
    m = _LINK_VALUE.match(value.strip())
    # A `key: Model/name` line is a link only when Model is a real type —
    # 'anchorPath: hooks/x.sh' must stay a property.
    if m and m.group(1) in _KNOWN_TYPES:
        entry.links.append((key, m.group(1), m.group(2).strip()))
        return
    entry.properties[key] = value.strip()


def parse(text: str, source: str = "") -> list[Entry]:
    entries: list[Entry] = []
    current: Entry | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        head = _HEAD.match(line)
        if head:
            current = Entry(type=head.group(2).strip(), name=head.group(3).strip(),
                            time=head.group(1), source=source, line=lineno)
            entries.append(current)
            continue
        cont = _CONT.match(line)
        if cont and current is not None:
            _continuation(current, cont.group(1), cont.group(2))
            continue
        if line.strip() and not line.startswith(" "):
            current = None  # a non-indented, non-bullet line ends the entry
    return entries


def frontmatter(text: str) -> dict:
    """The file's YAML-ish frontmatter as flat strings (fail-open: {})."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta
        m = _FRONTMATTER_KEY.match(line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip().strip('"')
    return {}


def parse_file(path: Path) -> tuple[dict, list[Entry]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}, []
    return frontmatter(text), parse(text, source=path.name)


def undistilled_files(context_dir: Path, project: str | None = None) -> list[Path]:
    """Active context files awaiting distillation, oldest first."""
    pattern = f"{project}__*.md" if project else "*.md"
    files = []
    for path in sorted(context_dir.glob(pattern)):
        meta, _ = ({}, None)
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:300]
        except OSError:
            continue
        if "distilled: false" in head:
            files.append(path)
    return files


def fold(entries: list[Entry]) -> dict[tuple[str, str], Entry]:
    """Merge repeated (type, name) statements: the LATEST values win — the
    log's churn resolved mechanically. Links and concepts union."""
    folded: dict[tuple[str, str], Entry] = {}
    for e in entries:
        key = (e.type, e.name)
        prev = folded.get(key)
        if prev is None:
            folded[key] = Entry(type=e.type, name=e.name, time=e.time,
                                properties=dict(e.properties),
                                links=list(e.links), concepts=list(e.concepts),
                                source=e.source, line=e.line)
            continue
        prev.properties.update(e.properties)
        for link in e.links:
            if link not in prev.links:
                prev.links.append(link)
        for concept in e.concepts:
            if concept not in prev.concepts:
                prev.concepts.append(concept)
        prev.time = e.time
    return folded
