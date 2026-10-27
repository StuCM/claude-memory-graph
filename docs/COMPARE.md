# Is the graph worth it? The 10-question comparison

Claude Code already remembers things on its own: `CLAUDE.md` files, and
**auto memory**, which is notes Claude writes per repository on this machine.
The graph only earns its complexity if it answers questions the built-in
memory can't. This check uses your own questions to find out, rather than
a benchmark.

## 1. Write your questions

Copy [`examples/compare-questions.toml`](../examples/compare-questions.toml)
and replace the examples with about 10 questions you have actually asked, or
wished Claude already knew the answer to:

```toml
[[question]]
text = "what did we decide about caching map tiles, and why?"
project = "quartz"            # the repo you'd be in when asking
expect = ["varnish"]          # words a right answer has to contain
```

Mix three kinds, because each favours a different memory:

- **inside one project**: built-in memory's home ground;
- **needing another project's knowledge** ("where else have we hit…"): what
  the graph claims to add;
- **phrased as the symptom**, not the fix ("the map shows deleted things"):
  this tests matching by meaning.

## 2. Run it

```sh
claude-memory-graph compare my-questions.toml
```

It writes `my-questions-report.md` next to the questions. For each question
it checks whether the expected words are within reach of:

| Column | What it checks |
|---|---|
| Graph, unprompted | what the gate injects with the prompt, exactly as in a session |
| Graph, when Claude looks | `memory_search`'s top hits plus a depth-2 recall of the first |
| Built-in, at start | the project's auto memory index (`MEMORY.md`, first 200 lines), your user `CLAUDE.md`, and the repo's `CLAUDE.md` if you gave `path` |
| Built-in, if opened | every auto memory topic file for that project |
| claude.ai | not checkable from here: ask it yourself and fill in the column |

The run uses a scratch log folder, so it doesn't add to the logs the miss
detector reads. In server mode, it checks a fresh copy of the server's graph.

## 3. Read it honestly

- A **✓ means reachable, not answered well.** The evidence lines show the
  text that matched, so read them before trusting a tick.
- **"Only the graph"** lists the questions that justify keeping it. If it's
  empty or only one or two, built-in memory covers what you ask, and the
  graph is mostly complexity.
- **"Only built-in"** lists knowledge the graph never captured. The fix is
  on the capture side: distill, or importing auto memory.
- Re-run it after a few weeks of use. Both memories grow.
