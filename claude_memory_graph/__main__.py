import argparse
import asyncio
import logging
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server

from .store import MemoryStore
from . import tools

log = logging.getLogger(__name__)

SERVER_INFO = {
    "name": "claude-memory-graph",
    "version": "0.1.0",
}

INSTRUCTIONS = (
    "Arches-inspired knowledge graph for Claude Code long-term memory. "
    "Each resource (Person, Project, Company, Task, Technology, Decision, Pattern) "
    "is its own named graph with scalar properties. Shared concepts (Skill, Concept, "
    "Constraint, Preference) enable multi-hop traversal between resources. "
    "RECALL FIRST: before re-deriving knowledge about a project, person, or past "
    "problem via searches or re-investigation, call memory_recall (depth 2) — "
    "decisions, rationale, gotchas, and preferences may already be recorded. "
    "When the exact name is unknown, memory_search finds ranked entry points "
    "from free text (names, labels, aliases, property text) — then recall one. "
    "The graph answers why/what-do-we-know questions; code-structure questions "
    "still belong to code search. "
    "Use memory_store_resource to create entities, memory_link to connect them, "
    "and memory_query for SPARQL."
)


def _store_path() -> Path:
    env = os.environ.get("MEMORY_GRAPH_PATH")
    if env:
        return Path(env)
    home = Path.home()
    return home / ".claude" / "memory-graph" / "store"


async def _run() -> None:
    store_path = _store_path()
    log.info("Opening memory store at: %s", store_path)
    store = MemoryStore.open_or_create(store_path)

    # Auto-distill: every new session's server starts by promoting the log's
    # structured entries (promote-only, idempotent, fail-open) — see distill.py.
    from . import distill as distill_mod
    report = distill_mod.auto_distill(store)
    if report and report.stored:
        log.info("auto-distill: %d node(s), %d link(s), %d residue",
                 len(report.stored), report.linked, len(report.residue))

    server = Server(SERVER_INFO["name"])
    server.instructions = INSTRUCTIONS
    tools.register(server, store)

    log.info("Starting MCP server (stdio)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

    log.info("Shutting down, saving graph...")
    store.save()
    log.info("Done")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claude-memory-graph",
        description="MCP memory graph server. With no subcommand, serves MCP over stdio. "
        "Subcommands are read-only terminal helpers (writes must go through the MCP "
        "server so a live session's save does not overwrite them).",
    )
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("recall", help="recall a resource and its links")
    p.add_argument("model", help="e.g. Person, Project")
    p.add_argument("name")
    p.add_argument("--depth", type=int, default=1, choices=[1, 2])
    p = sub.add_parser("reflect", help="graph overview: counts, relations, recent")
    p.add_argument("model", nargs="?", default=None)
    p = sub.add_parser("query", help="run a SPARQL query")
    p.add_argument("sparql")
    p = sub.add_parser("ask", help="natural-language question → composed SPARQL "
                                   "(query planner v0)")
    p.add_argument("text")
    p.add_argument("--explain", action="store_true",
                   help="show the grounding table and composed SPARQL")
    p = sub.add_parser("search", help="fuzzy entry-point search by free text")
    p.add_argument("text")
    p.add_argument("--model", default=None, help="filter: resource model or concept type")
    p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser(
        "distill",
        help="mechanical distill: promote structured context entries to the graph "
             "(no LLM). The one WRITING subcommand — run it between sessions: a "
             "live MCP server's next save would overwrite CLI writes.")
    p.add_argument("--dry-run", action="store_true", help="report without writing")
    p.add_argument("--keep", action="store_true", help="don't archive clean files")
    p.add_argument("--project", default=None, help="only this project's context files")
    p.add_argument("--context-dir", type=Path, default=None)
    sub.add_parser("misses", help="gate miss report: silences followed by explicit recalls")
    sub.add_parser("asks", help="planner telemetry: outcomes, misgrounding suspects, "
                                "vocabulary gaps (from ask-decisions.jsonl)")
    p = sub.add_parser("gaps", help="mechanical link-gap report: orphans, conceptless "
                                    "nodes, unlinked pairs sharing rare vocabulary")
    p.add_argument("--limit", type=int, default=10, help="max pair suggestions")
    sub.add_parser("doctor", help="one-shot diagnosis: are hooks firing? do the CLI "
                                  "and plugin agree on paths? is the graph populated "
                                  "and linked? prints a prioritised verdict.")
    p = sub.add_parser("pulse", help="one screen: is memory reaching sessions? "
                                     "(injections, capture enforcement, misses, backlog)")
    p.add_argument("--days", type=int, default=7)
    p = sub.add_parser("dashboard", help="generate a self-contained HTML dashboard "
                                         "from the logs (open the printed path)")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--out", type=Path, default=None)
    p = sub.add_parser("serve", help="run the MCP server over streamable HTTP so "
                                     "other machines/clients share this memory. "
                                     "One process owns the store (safer than "
                                     "per-session stdio servers). Non-localhost "
                                     "binds require --token.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8848)
    p.add_argument("--token", default=os.environ.get("MEMORY_GRAPH_TOKEN", ""),
                   help="bearer token clients must send (env: MEMORY_GRAPH_TOKEN)")
    p = sub.add_parser("gate", help="preview the injection decision for a prompt — "
                                    "the REAL gate math (both layers, thresholds, "
                                    "scores), zero side effects. memory_search is "
                                    "NOT this; use gate to answer 'what would my "
                                    "prompt inject?'")
    p.add_argument("prompt")
    p.add_argument("--project", default="",
                   help="apply the proximity prior + session-log layer for this project")
    p.add_argument("--show", type=int, default=6, help="candidates to display per layer")
    p = sub.add_parser("coverage", help="grounding-coverage experiment over real prompts")
    p.add_argument("--prompts", type=Path, default=None,
                   help="text file, one prompt per line")
    p.add_argument("--transcripts", type=Path, nargs="*", default=None,
                   help="Claude Code transcript .jsonl files or directories "
                        "(e.g. ~/.claude/projects)")
    args = parser.parse_args()

    if args.cmd is None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        asyncio.run(_run())
        return

    if args.cmd == "misses":
        from .gate import misses
        print(misses.report())
        return

    if args.cmd == "asks":
        from . import planner
        print(planner.asks_report())
        return

    if args.cmd == "gaps":
        from . import gaps as gaps_mod
        store = MemoryStore.open_or_create(_store_path())
        print(gaps_mod.handle(store, limit=args.limit))
        return

    if args.cmd == "doctor":
        from .gate import doctor
        print(doctor.report())
        return

    if args.cmd == "pulse":
        from .gate import pulse
        print(pulse.report(days=args.days))
        return

    if args.cmd == "dashboard":
        from .gate import dashboard
        print(dashboard.write(out=args.out, days=args.days))
        return

    if args.cmd == "serve":
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
        from .http_server import serve
        serve(_store_path(), INSTRUCTIONS, host=args.host, port=args.port,
              token=args.token)
        return

    if args.cmd == "gate":
        from .gate import preview
        print(preview.preview(args.prompt, project=args.project, show=args.show))
        return

    if args.cmd == "distill":
        from . import distill as distill_mod
        store = MemoryStore.open_or_create(_store_path())
        report = distill_mod.distill(
            store, directory=args.context_dir, project=args.project,
            dry_run=args.dry_run, keep=args.keep)
        print(report.render())
        return

    if args.cmd == "coverage":
        from .gate import coverage
        prompts: list[str] = []
        if args.prompts:
            prompts += coverage.prompts_from_file(args.prompts)
        if args.transcripts:
            prompts += coverage.prompts_from_transcripts(args.transcripts)
        if not prompts:
            print("No prompts. Pass --prompts FILE and/or --transcripts PATH "
                  "(see docs/tasks/grounding-coverage-experiment.md).")
            return
        store = MemoryStore.open_or_create(_store_path())
        print(coverage.report(store, prompts))
        return

    from .tools import recall, reflect, query, search

    store = MemoryStore.open_or_create(_store_path())
    if args.cmd == "recall":
        print(recall.handle(store, args.model, args.name, args.depth))
    elif args.cmd == "reflect":
        print(reflect.handle(store, args.model))
    elif args.cmd == "query":
        print(query.handle(store, args.sparql))
    elif args.cmd == "search":
        print(search.handle(store, args.text, args.model, args.limit))
    elif args.cmd == "ask":
        from . import planner
        print(planner.handle(store, args.text, explain=args.explain))


if __name__ == "__main__":
    main()
