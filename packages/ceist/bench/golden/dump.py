"""The whole grounding of every bench question, one JSON line each: the golden file
a refactor of ground() must reproduce byte for byte, and the TypeScript port's fixture.

    cd <starches-demo>/ask && PYTHONPATH=<repo>/packages/ceist/src uv run python <this> demo
    .venv-ceist/bin/python <this> her <arches-her pkg> <her.bundle.json>
    .venv-ceist/bin/python <this> bench <lingo | catalina | her>    # one process per set

Writes demo.jsonl, her.jsonl or bench-<set>.jsonl beside this file.
"""
import json
import os
import sys
from dataclasses import fields, is_dataclass
from datetime import date
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":    # set order in ground is hash order
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})

from ceist import interpret, narrate  # noqa: E402
from ceist.questions import fill, target_of  # noqa: E402
from ceist.vocabulary import DateField, Entity, Group, Value  # noqa: E402

HERE = Path(__file__).parent
TODAY = date(2026, 11, 8)


def plain(o):
    if isinstance(o, Entity):
        return o.id
    if isinstance(o, Group):
        return f"{o.model}.{o.name}"
    if isinstance(o, DateField):
        return o.field
    if isinstance(o, Value):
        return f"{o.field}={o.value}"
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if is_dataclass(o):
        return {f.name: getattr(o, f.name) for f in fields(o)}
    raise TypeError(type(o))


def line(name: str, q: str, vocab, matcher=None) -> str:
    m = interpret(vocab, q, TODAY, matcher)
    shown = m.plan or m.detail
    return json.dumps({"set": name, "q": q, "grounding": m.grounding, "refused": m.refused,
                       "plan": narrate(shown) if shown else None, "target": target_of(m)},
                      default=plain, ensure_ascii=False)


def demo():
    sys.path.insert(0, str(Path.cwd()))
    import ask
    vocab, _, matcher, _ = ask.startup()
    yield from (line("bank", o["q"], vocab, matcher)
                for o in json.loads((HERE.parent / "demo" / "questions.json").read_text())["questions"])
    for name in ("train", "holdout"):
        path = Path.home() / ".cache" / "ceist-questions-demo" / f"{name}.json"
        for o in json.loads(path.read_text())["questions"]:
            q = fill(o["q"], vocab)
            if q is not None:
                yield line(name, q, vocab, matcher)


def her(pkg: str, bundle: str):
    from ceist import config
    from ceist.pipeline import _vocabulary
    vocab = _vocabulary(Path(pkg) / "graphs" / "resource_models", Path(pkg) / "reference_data",
                        json.loads(Path(bundle).read_text()))
    matcher = config.chain(config.load(HERE.parent / "her" / "ceist.toml"))
    for c in json.loads((HERE.parent / "her" / "cases.json").read_text())["cases"]:
        yield line("her", c["q"], vocab, matcher)


def bench(name: str):
    sys.path.insert(0, str(HERE.parent / "ontology"))
    import run

    from ceist.arches import ArchesVocabulary
    from ceist.questions import templated
    graphs = run.graph_docs(run.SETS[name])
    resources = run.synthetic(graphs)
    items = templated(ArchesVocabulary(graphs, resources=resources), run.load_ontology())
    for mode, b in {"none": None, **run.layer_bundles(name, graphs)}.items():
        vocab = ArchesVocabulary(graphs, resources=resources, bundle=b)
        yield from (line(f"{name}/{mode}", fill(o["q"], vocab), vocab) for o in items)


if __name__ == "__main__":
    kind, *args = sys.argv[1:]
    name = f"bench-{args[0]}" if kind == "bench" else kind
    (HERE / f"{name}.jsonl").write_text("".join(row + "\n" for row in {"demo": demo, "her": her, "bench": bench}[kind](*args)))
