"""Domain-adapt WordLlama to a project's vocabulary, without leaving the browser.

    uv run --with jax --with optax python packages/ceist/bench/adapt.py \\
        --vocab her/vocab --models her/models --kind linear --out her/adapter-linear.npz

Training data is the LLM-built vocabulary itself: each phrasing should land
nearer its own entry than the entries it could be confused with — the
same model's entries of the same kind (date / link / property), which is
exactly the shortlist the planner hands the matcher at query time.

Two kinds, both still static (a lookup and an average at query time):
- linear: one 256×256 matrix applied to WordLlama's vectors (128 KB as
  float16), initialised to the identity and pulled back towards it;
- tokens: small corrections to the table rows of the words the vocabulary
  uses, pulled back towards zero (general English elsewhere is untouched).

20% of each entry's phrasings are held out to pick the stopping point and
report how well unseen phrasings are placed. The project's test questions
are never used here.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2]))
DATE = {"date", "edtf"}


def kind_of(node):
    if node["datatype"] in DATE:
        return "date"
    if node["datatype"].startswith("resource-instance"):
        return "link"
    return "property"


def held_out(text: str) -> bool:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16) % 5 == 0


def load(vocab_dir: Path, models_dir: Path):
    """Entries (model, kind, phrasings) and a train/val split of phrasings."""
    entries, items = [], []           # items: (text, entry index, is_val)
    for p in sorted(vocab_dir.glob("*.json")):
        v = json.loads(p.read_text())
        nodes = {n["alias"]: n for n in json.loads(
            (models_dir / f"{v['model']}.json").read_text())["nodes"]}
        for e in v["entries"]:
            n = nodes.get(e["node"])
            if n is None:
                continue
            k = len(entries)
            entries.append((v["model"], kind_of(n)))
            phr = sorted(set(e["phrases"]))
            for t in phr:
                items.append((t, k, len(phr) >= 4 and held_out(t)))
    return entries, items


def ids_matrix(enc, texts, width=8):
    import re
    word = re.compile(r"\w+")
    rows = [enc._ids(word.findall(t))[:width] for t in texts]
    ids = np.zeros((len(rows), width), dtype=np.int32)
    mask = np.zeros((len(rows), width), dtype=np.float32)
    for i, r in enumerate(rows):
        ids[i, :len(r)], mask[i, :len(r)] = r, 1
    return ids, mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", default=str(HERE / "her" / "vocab"))
    ap.add_argument("--models", default=str(HERE / "her" / "models"))
    ap.add_argument("--kind", choices=["linear", "tokens"], default="linear")
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--reg", type=float, default=1.0)
    ap.add_argument("--scale", type=float, default=20.0)
    a = ap.parse_args()

    import jax
    import jax.numpy as jnp
    import optax
    from claude_memory_graph.gate import semantic

    enc = semantic.encoder()
    E0 = np.asarray(enc.weights, dtype=np.float32)
    entries, items = load(Path(a.vocab), Path(a.models))
    texts = [t for t, _, _ in items]
    owner = np.array([k for _, k, _ in items])
    is_val = np.array([v for _, _, v in items])
    ids, mask = ids_matrix(enc, texts)
    enc.save_cache()

    # candidates: entries of the same model and kind (the planner's shortlist)
    groups = {}
    for k, key in enumerate(entries):
        groups.setdefault(key, []).append(k)
    width = max(len(g) for g in groups.values())
    cands = np.zeros((len(items), width), dtype=np.int32)
    cmask = np.zeros((len(items), width), dtype=bool)
    target = np.zeros(len(items), dtype=np.int32)
    for i, k in enumerate(owner):
        g = groups[entries[k]]
        cands[i, :len(g)], cmask[i, :len(g)] = g, True
        target[i] = g.index(k)
    # an entry's prototype: the mean of its TRAINING phrasings
    proto_w = np.zeros((len(entries), len(items)), dtype=np.float32)
    for i, k in enumerate(owner):
        if not is_val[i]:
            proto_w[k, i] = 1
    proto_w /= np.maximum(proto_w.sum(1, keepdims=True), 1)

    vocab_tokens = np.unique(ids[mask > 0])
    tok_index = np.full(E0.shape[0], -1, dtype=np.int32)
    tok_index[vocab_tokens] = np.arange(len(vocab_tokens))

    ids_j, mask_j = jnp.array(ids), jnp.array(mask)
    E0_j = jnp.array(E0)

    def norm(x):
        return x / (jnp.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)

    def vectors(params):
        if a.kind == "tokens":
            rows = E0_j[ids_j] + params["delta"][jnp.array(tok_index)[ids_j]] * (ids_j[..., None] >= 0)
        else:
            rows = E0_j[ids_j]
        v = norm((rows * mask_j[..., None]).sum(1) / jnp.maximum(mask_j.sum(1, keepdims=True), 1))
        if a.kind == "linear":
            v = norm(v @ params["A"])
        return v

    def logits(params):
        v = vectors(params)
        protos = norm(jnp.array(proto_w) @ v)
        s = a.scale * jnp.einsum("id,icd->ic", v, protos[jnp.array(cands)])
        return jnp.where(jnp.array(cmask), s, -1e9)

    train = jnp.array(~is_val)

    def loss(params):
        lp = jax.nn.log_softmax(logits(params))
        nll = -jnp.take_along_axis(lp, jnp.array(target)[:, None], 1)[:, 0]
        data = (nll * train).sum() / train.sum()
        if a.kind == "linear":
            reg = jnp.sum((params["A"] - jnp.eye(E0.shape[1])) ** 2)
        else:
            reg = jnp.sum(params["delta"] ** 2)
        return data + a.reg * 1e-3 * reg

    def accuracy(params, which):
        pred = np.asarray(jnp.argmax(logits(params), 1))
        sel = is_val if which == "val" else ~is_val
        return float((pred[sel] == target[sel]).mean())

    params = ({"A": jnp.eye(E0.shape[1])} if a.kind == "linear"
              else {"delta": jnp.zeros((len(vocab_tokens), E0.shape[1]))})
    opt = optax.adam(a.lr)
    state = opt.init(params)
    step = jax.jit(lambda p, s: _step(p, s))

    def _step(p, s):
        val, g = jax.value_and_grad(loss)(p)
        upd, s = opt.update(g, s, p)
        return optax.apply_updates(p, upd), s, val

    print(f"{len(entries)} entries, {len(items)} phrasings "
          f"({int(is_val.sum())} held out), {len(vocab_tokens)} vocabulary tokens")
    best = (accuracy(params, "val"), 0, params)
    print(f"step 0: train {accuracy(params, 'train'):.3f}  held-out {best[0]:.3f}  (WordLlama as is)")
    for i in range(1, a.steps + 1):
        params, state, val = step(params, state)
        if i % 50 == 0:
            acc = accuracy(params, "val")
            print(f"step {i}: loss {float(val):.3f}  train {accuracy(params, 'train'):.3f}  held-out {acc:.3f}")
            if acc > best[0]:
                best = (acc, i, params)
    acc, at, params = best
    print(f"kept step {at}: held-out {acc:.3f}")
    out = {"kind": a.kind, "heldout": acc, "step": at}
    if a.kind == "linear":
        out["A"] = np.asarray(params["A"], dtype=np.float16)
    else:
        out["tokens"] = vocab_tokens
        out["delta"] = np.asarray(params["delta"], dtype=np.float16)
    np.savez_compressed(a.out, **out)
    print(f"wrote {a.out} ({Path(a.out).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
