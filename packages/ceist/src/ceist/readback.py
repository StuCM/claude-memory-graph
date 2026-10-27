"""Read-back: a compiled query turned back into a plan, and checked against
what the question was understood to mean.

Each output (Rós Madair, Arches Search) can decompile what it is about to
send. Narrating both in canonical form (relation and field names, conditions
in a fixed order) and comparing them catches a compiler that dropped, flipped
or misplaced a condition — before the query runs. The runners refuse to run
on a mismatch, and `explain` shows both readings side by side.
"""

from dataclasses import dataclass

from .narrate import narrate
from .plan import Plan


@dataclass
class Check:
    ok: bool
    meant: str          # what the question was understood as (canonical)
    said: str           # what the compiled query says (canonical)
    readable: str       # what the compiled query says, for people

    def lines(self) -> list[str]:
        out = ["── query says ──", "  " + self.readable]
        out.append("  ✓ matches what was understood" if self.ok else
                   f"  ✗ differs from what was understood:\n    meant: {self.meant}\n"
                   f"    query: {self.said}")
        return out


def check(meant: Plan, said: Plan) -> Check:
    a, b = narrate(meant, canonical=True), narrate(said, canonical=True)
    return Check(a == b, a, b, narrate(said))
