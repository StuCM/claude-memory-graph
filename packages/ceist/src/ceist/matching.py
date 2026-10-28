"""Matching: which vocabulary item does a phrase mean?

The planner finds a phrase that needs a meaning ("put up", "touched", "by"),
narrows the candidates by structure (the slot: a date of this model, a link to
a Person, a relation between these two types), and hands both to a Chain of
layers. Each layer decides, defers or gives up:

    Match       one item, confidently            → the chain stops
    Ambiguous   several items, too close to call → the next layer may settle it
    NoMatch     nothing fits (with near misses)  → the next layer tries

When no layer decides, the chain offers the closest items ("did you mean …?")
or refuses — it never guesses. Every decision names the layer that made it,
so explain output says how a word was understood.

Layers (configured per project, see ceist.config):

    exact     the phrase is one of an item's phrasings, or covers most of one
              (optionally on word roots: built / build / building); a phrase
              saying "from" never matches a phrasing saying "to"
    vectors   static word vectors (ceist.vectors): the item whose closest
              phrasing clears `min` and beats the runner-up by `gap`
"""

import re
from dataclasses import dataclass, field

FROM = {"from", "leaving", "departing", "departed", "left", "out"}
TO = {"to", "towards", "toward", "into", "bound", "arriving", "arrived", "reaching"}
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Item:
    """Something a phrase can mean."""
    key: object                                  # identity (relation name, (node, qualifier, end))
    phrases: tuple[str, ...]                     # its phrasings, lowercase
    label: str = ""                              # how it reads in "did you mean"
    payload: object = field(default=None, compare=False, hash=False)   # what the planner uses


@dataclass
class Match:
    item: Item
    score: float
    layer: str


@dataclass
class Ambiguous:
    ranked: list[tuple[float, Item]]
    layer: str


@dataclass
class NoMatch:
    ranked: list[tuple[float, Item]] = field(default_factory=list)   # near misses, best first
    layer: str = ""


@dataclass
class Resolution:
    match: Match | None = None
    options: list[Item] = field(default_factory=list)   # "did you mean", best first
    notes: list[str] = field(default_factory=list)


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def clash(phrase_words: set[str], phrasing: str) -> bool:
    """A phrase saying "from" against a phrasing saying "to", or the reverse:
    static vectors can't tell them apart, so the matcher must."""
    w = set(words(phrasing))
    return bool((phrase_words & FROM and w & TO and not w & FROM)
                or (phrase_words & TO and w & FROM and not w & TO))


def _light_root(w: str) -> str:
    for suf in ("ings", "ing", "ied", "ies", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)] + ("y" if suf in ("ied", "ies") else "")
    return w


def _rooter():
    try:
        import simplemma
        return lambda w: simplemma.lemmatize(w, lang="en")
    except ImportError:                      # fail open to a light suffix rule
        return _light_root


class Exact:
    name = "exact"

    def __init__(self, roots: bool = False, direction: bool = True):
        self.direction = direction
        self.root = _rooter() if roots else (lambda w: w)

    def norm(self, text: str) -> str:
        return " ".join(self.root(w) for w in words(text))

    @staticmethod
    def _covers(inner: str, outer: str) -> bool:
        """`inner` appears in `outer` as whole words and is most of it — so a
        phrasing "metal" doesn't claim "turned up by metal detectorists"."""
        return f" {inner} " in f" {outer} " and len(inner.split()) * 2 >= len(outer.split())

    def decide(self, phrase: str, items: list[Item], context: str = ""):
        p, pw = self.norm(phrase), set(words(phrase))
        best: dict[object, tuple[int, Item]] = {}
        for it in items:
            for ph in it.phrases:
                if self.direction and clash(pw, ph):
                    continue
                v = self.norm(ph)
                if not v:
                    continue
                if v == p:
                    s = 3
                elif self._covers(v, p) or self._covers(p, v):
                    s = 1 + (len(v) > 3)
                else:
                    continue
                if s > best.get(it.key, (0, None))[0]:
                    best[it.key] = (s, it)
        if not best:
            return NoMatch(layer=self.name)
        top = max(s for s, _ in best.values())
        winners = [it for s, it in best.values() if s == top]
        if len(winners) == 1:
            return Match(winners[0], 1.0, self.name)
        return Ambiguous([(1.0, it) for it in winners], self.name)


class Vectors:
    name = "vectors"

    def __init__(self, encoder, low: float = 0.6, gap: float = 0.08, direction: bool = True):
        self.enc, self.low, self.gap, self.direction = encoder, low, gap, direction
        self._cache: dict[str, object] = {}

    def vec(self, text: str):
        if text not in self._cache:
            self._cache[text] = self.enc.encode([text])[0]
        return self._cache[text]

    def decide(self, phrase: str, items: list[Item], context: str = ""):
        if not items:
            return NoMatch(layer=self.name)
        pv, pw = self.vec(phrase), set(words(phrase))
        scored = []
        for it in items:
            texts = list(it.phrases) + ([it.label] if it.label else [])
            s = max(float(pv @ self.vec(t)) - (0.3 if self.direction and clash(pw, t) else 0.0)
                    for t in texts)
            scored.append((s, it))
        scored.sort(key=lambda x: -x[0])
        top = scored[0][0]
        if top < self.low:
            return NoMatch(scored, self.name)
        close = [x for x in scored if top - x[0] < self.gap]
        if len(close) == 1:
            return Match(scored[0][1], top, self.name)
        return Ambiguous(close, self.name)


class Chain:
    """Layers in order; the first Match wins. Otherwise the closest items are
    offered (clarify) — or nothing, when the project turns that off."""

    def __init__(self, layers: list, clarify_top: int = 3, clarify_min: float = 0.3):
        self.layers, self.clarify_top, self.clarify_min = layers, clarify_top, clarify_min

    def resolve(self, phrase: str, items: list[Item], context: str = "") -> Resolution:
        out = Resolution()
        if not items:
            return out
        pool: list[tuple[float, Item]] = []
        for layer in self.layers:
            d = layer.decide(phrase, items, context)
            if isinstance(d, Match):
                out.match = d
                out.notes.append(f"'{phrase}' → {d.item.label or d.item.key} ({d.layer}"
                                 + (f" {d.score:.2f})" if d.layer != "exact" else ")"))
                return out
            if isinstance(d, Ambiguous):
                out.notes.append(f"'{phrase}': {d.layer} can't choose between "
                                 + ", ".join(it.label or str(it.key) for _, it in d.ranked[:3]))
                pool = d.ranked + pool
            elif d.ranked:
                pool += [x for x in d.ranked if x[0] >= self.clarify_min]
        seen, options = set(), []
        for _, it in sorted(pool, key=lambda x: -x[0]):
            if it.key not in seen:
                seen.add(it.key)
                options.append(it)
        out.options = options[: self.clarify_top]
        return out
