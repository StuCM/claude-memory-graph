"""Every controlled node of an Arches package resolves to a loaded list.

    python packages/ceist/bench/her_lists.py <package dir>    # e.g. arches_her/pkg

Reads graphs/resource_models and reference_data (controlled_lists/,
collections/, concepts/) the way ceist does, through Alizarin, and fails
if any reference or concept node names a list that didn't load: its values
could never be asked for. Prints how many nodes of each kind there are and
how many values a question can name.
"""

import sys
from collections import Counter
from pathlib import Path

from ceist.arches import (
    CONCEPT_TYPES,
    REFERENCE_TYPES,
    ArchesVocabulary,
    collection_of,
    graph_doc,
    load_reference_data,
)
from ceist.arches_describe import reference_files


def main(pkg: str) -> int:
    root = Path(pkg)
    graphs = [graph_doc(p) for p in sorted((root / "graphs" / "resource_models").glob("*.json"))]
    rdm, alts = load_reference_data(reference_files(root / "reference_data"))
    vocab = ArchesVocabulary(graphs, rdm, alt_labels=alts)
    kinds, missing = Counter(), Counter()
    for m in vocab.models.values():
        for n in m.nodes:
            dt = n.get("datatype")
            if dt in REFERENCE_TYPES | CONCEPT_TYPES:
                kinds["controlled list" if dt in REFERENCE_TYPES else "concept (legacy)"] += 1
                cid = collection_of(n)
                if not (cid and rdm.has_collection(cid)):
                    missing[f"{m.name}.{n.get('alias')} → {cid}"] += 1
    print(f"{len(vocab.models)} models; nodes: "
          + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
          + f"; {len(vocab.values())} values a question can name")
    for m in sorted(missing)[:20]:
        print(f"  ! no list loaded for {m}", file=sys.stderr)
    if missing:
        print(f"{len(missing)} controlled node(s) name a list that didn't load", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
