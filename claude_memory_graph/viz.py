"""Render the memory graph as a self-contained interactive HTML page (read-only)."""

import json
from pathlib import Path

from .namespaces import SPARQL_PREFIXES
from .store import MemoryStore

_TEMPLATE = Path(__file__).parent / "viz_template.html"

_NODES_SPARQL = SPARQL_PREFIXES + """
SELECT ?s ?type ?name ?label ?desc ?rationale WHERE {
  GRAPH ?g {
    ?s a ?type .
    OPTIONAL { ?s mem:name ?name }
    OPTIONAL { ?s mem:label ?label }
    OPTIONAL { ?s mem:description ?desc }
    OPTIONAL { ?s mem:rationale ?rationale }
  }
  FILTER(STRSTARTS(STR(?s), "https://memory.claude.local/ontology#resource/")
      || STRSTARTS(STR(?s), "https://memory.claude.local/ontology#concept/"))
}
"""

_EDGES_SPARQL = SPARQL_PREFIXES + """
SELECT ?src ?tgt ?rel WHERE {
  GRAPH ?g {
    ?l a mem:CrossLink ;
       mem:linkSource ?src ;
       mem:linkTarget ?tgt ;
       mem:linkRelation ?rel .
    OPTIONAL { ?l mem:linkValidTo ?vt }
  }
  FILTER(!BOUND(?vt))
}
"""


def extract(store: MemoryStore) -> dict:
    nodes: dict[str, dict] = {}
    for sol in store.query(_NODES_SPARQL):
        s = sol["s"].value
        type_iri = sol["type"].value
        tname = type_iri.rsplit("#", 1)[-1]
        val = lambda k: sol[k].value if sol[k] is not None else None
        label = val("name") or val("label") or s.rsplit("/", 1)[-1][:8]
        nodes[s] = {
            "id": s,
            "label": label,
            "type": tname,
            "kind": "concept" if "#concept/" in s else "resource",
            "desc": val("desc") or val("rationale") or "",
        }

    edges = []
    for sol in store.query(_EDGES_SPARQL):
        src, tgt = sol["src"].value, sol["tgt"].value
        if src in nodes and tgt in nodes:
            edges.append({"s": src, "t": tgt, "rel": sol["rel"].value})

    for n in nodes.values():
        n["deg"] = 0
    for e in edges:
        nodes[e["s"]]["deg"] += 1
        nodes[e["t"]]["deg"] += 1

    return {"nodes": list(nodes.values()), "edges": edges}


def _serve_and_open(html: str) -> None:
    """Open via localhost, not file:// — snap-confined browsers (Ubuntu's
    default Firefox) cannot read dot-directories under $HOME, so a file://
    URL into ~/.claude silently shows nothing."""
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    body = html.encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving at {url} — Ctrl+C to stop", flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def handle(store: MemoryStore, out: Path | None, open_browser: bool = True) -> str:
    out = out or Path.home() / ".claude" / "memory-graph" / "viz.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = extract(store)
    html = _TEMPLATE.read_text().replace("__GRAPH_DATA__", json.dumps(data))
    out.write_text(html)
    msg = f"Wrote {out} ({len(data['nodes'])} nodes, {len(data['edges'])} links)"
    if open_browser:
        print(msg, flush=True)
        _serve_and_open(html)
        return ""
    return msg
