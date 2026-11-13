"""Every link's real targets, its inverse, and whether its model is a join record: the
`"links"` of a bundle (`ceist.vocab/3`), read by the planner to refuse joins the data never makes."""

from .arches import LINK_TYPES

JOIN_MIN_MODELS = 2      # a join record links at least this many different models ...


def build(vocab) -> dict[str, dict]:
    """{"<Model>.<alias>": {"targets", "from": schema|records|crm, "inverse", "join"}} for an
    ArchesVocabulary; a join record (links to 2+ models, no name of its own) is a rule's proposal, for the LLM to confirm later."""
    links: dict[str, dict] = {}
    reaches: dict[str, set[str]] = {}
    joins = set()
    for m in vocab.models.values():
        named = any(n.get("alias") == "name" or str(n.get("alias")).endswith("_name") for n in m.nodes)
        for n in m.nodes:
            if n.get("datatype") in LINK_TYPES and n.get("alias"):
                targets, source = vocab.ends_of(m.name, n["alias"])
                links[f"{m.name}.{n['alias']}"] = {"targets": sorted(targets), "from": source,
                                                   "inverse": None, "join": False}
                reaches.setdefault(m.name, set()).update(targets)
        if len(reaches.get(m.name, ())) >= JOIN_MIN_MODELS and not named:
            joins.add(m.name)
    for key, entry in links.items():
        model, alias = key.rsplit(".", 1)
        entry["join"] = model in joins
        if len(entry["targets"]) == 1:
            back = [k.rsplit(".", 1)[1] for k, e in links.items()
                    if k.rsplit(".", 1)[0] == entry["targets"][0] and e["targets"] == [model]]
            if len(back) == 1:
                entry["inverse"] = back[0]
    return links
