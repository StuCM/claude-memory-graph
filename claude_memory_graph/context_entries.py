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
# Keys are lowercase by convention — camelCase properties (anchorPath,
# sourceContext) and lowercase relations (affects, relatesTo). Prose
# written as "  Symptom: the page 500s" or "  Stuart: I'm nervous..."
# otherwise invents a property and a junk predicate in the ontology
# namespace; ~100 of them reached one real graph that way.
_CONT = re.compile(r"^ {2,}([a-z][A-Za-z0-9_]*):\s+(.+)$")
_LINK_VALUE = re.compile(r"^([A-Z][A-Za-z]*)/(.+)$")
# `key: >` / `key: |` (with optional chomping) — the value is the indented
# block beneath, not the indicator. The protocol asks for one-line values, but
# the shape reads as YAML so long values get written this way; parsing only the
# indicator silently dropped the content and stored a literal ">".
_BLOCK_SCALAR = re.compile(r"^[>|][-+]?$")
_FRONTMATTER_KEY = re.compile(r"^(\w+):\s*(.*)$")

# Head categories that are narrative-only lanes (never mechanical models);
# everything else must be a RESOURCE_MODEL to be promotable.
_KNOWN_TYPES = set(RESOURCE_MODELS) | set(CONCEPT_TYPES)

# The protocol's worked examples use narrative head words ("Problem:",
# "User preference:"), so real logs are overwhelmingly written with them —
# they carry the same structure as a Decision entry and mean a specific
# model. Map the knowledge-shaped ones on; heads that describe a moment
# rather than durable knowledge (Scope, Open, Outcome, Status, Implemented,
# Deliverable) stay unmapped and fall to the LLM lane on purpose.
HEAD_MODEL = {
    "Discovery": "Pattern",
    "Problem": "Pattern",
    "Gotcha": "Pattern",
    "Finding": "Pattern",
    "Investigation finding": "Pattern",
    "Codebase orientation": "Pattern",
    "Note": "Pattern",
    "Reference": "Pattern",
    "Correction": "Pattern",
    "User preference": "Preference",
    "User correction": "Preference",
}


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
    def model(self) -> str:
        """The graph model this entry promotes to: its head word, or what
        that head word means (HEAD_MODEL)."""
        return HEAD_MODEL.get(self.type, self.type)

    @property
    def promotable(self) -> bool:
        """Mechanically promotable: structured AND the head resolves to a
        graph model (a resource, or a concept type such as Preference)."""
        return self.structured and (
            self.model in RESOURCE_MODELS or self.model in CONCEPT_TYPES
        )

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


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block_value(lines: list[str], start: int, indent: int) -> tuple[str, int]:
    """Gather a YAML block scalar's body: the lines below `start` indented
    deeper than its key. Folded to one line — these become single graph
    properties, so the line breaks carry nothing. Returns (value, next index)."""
    body: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():          # blank lines belong to the block
            i += 1
            continue
        if _indent(line) <= indent:   # dedent ends it
            break
        body.append(line.strip())
        i += 1
    return " ".join(body), i


def parse(text: str, source: str = "") -> list[Entry]:
    entries: list[Entry] = []
    current: Entry | None = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = i + 1
        head = _HEAD.match(line)
        if head:
            current = Entry(type=head.group(2).strip(), name=head.group(3).strip(),
                            time=head.group(1), source=source, line=lineno)
            entries.append(current)
            i += 1
            continue
        cont = _CONT.match(line)
        if cont and current is not None:
            key, value = cont.group(1), cont.group(2).strip()
            i += 1
            if _BLOCK_SCALAR.match(value):
                value, i = _block_value(lines, i, _indent(line))
            if value:  # an empty block stores nothing, never the bare indicator
                _continuation(current, key, value)
            continue
        if line.strip() and not line.startswith(" "):
            current = None  # a non-indented, non-bullet line ends the entry
        i += 1
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
