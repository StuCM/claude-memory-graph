"""Test doubles shared by the ceist tests."""



class FakeEncoder:
    """Deterministic vectors: each distinct word its own direction (no
    collisions); words in SAME share their partner's."""
    SAME = {"erected": "built", "constructed": "built", "raised": "built",
            "demolished": "destroyed", "flattened": "destroyed"}

    @staticmethod
    def ready() -> bool:
        try:
            import numpy  # noqa: F401
            return True
        except ImportError:
            return False

    DIM = 512
    index: dict[str, int] = {}

    def encode(self, texts):
        import numpy as np
        out = []
        for t in texts:
            v = np.zeros(self.DIM)
            for w in t.lower().split():
                w = self.SAME.get(w, w)
                v[self.index.setdefault(w, len(self.index))] += 1
            out.append(v / (np.linalg.norm(v) or 1))
        return np.array(out)
