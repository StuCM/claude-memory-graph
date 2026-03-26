# Claude Memory Graph — Architecture Guide

A complete guide to how this system works, written for someone new to Rust. Covers the high-level design, every file in detail, and the Rust patterns used throughout.

---

## Table of Contents

1. [What This System Does](#what-this-system-does)
2. [The Big Picture](#the-big-picture)
3. [Key Concepts You Need First](#key-concepts-you-need-first)
4. [File-by-File Walkthrough](#file-by-file-walkthrough)
5. [Data Flow: What Happens When...](#data-flow-what-happens-when)
6. [Rust Patterns Used](#rust-patterns-used)
7. [SPARQL Queries Explained](#sparql-queries-explained)
8. [How to Run and Test](#how-to-run-and-test)

---

## What This System Does

This is an **MCP server** — a program that Claude Code talks to over stdin/stdout using JSON-RPC messages. It gives Claude tools to store and retrieve structured knowledge as a graph.

Think of it like a database, but instead of tables with rows, it stores **entities** (people, projects, technologies) as mini-databases (graphs) connected by **relationships** (links).

The goal: when Claude is working on your project and needs context, it can query this graph to find relevant information — not just what's directly stored, but what's connected. "Stuart works on Memory Graph, Memory Graph uses Rust" → Claude knows Rust is relevant when talking to Stuart.

---

## The Big Picture

```
┌─────────────────────────────────────────────────────┐
│ Claude Code (the client)                            │
│                                                      │
│ Sends JSON-RPC messages over stdin:                  │
│   "Create Person named Stuart"                       │
│   "Link Stuart → worksOn → Memory Graph"             │
│   "Recall everything about Stuart"                   │
└──────────────┬──────────────────────────┬────────────┘
               │ stdin (JSON)             │ stdout (JSON)
               ▼                          │
┌──────────────────────────────────────────────────────┐
│ MCP Server (this program)                            │
│                                                      │
│  main.rs          → starts the server                │
│  tools/mod.rs     → routes incoming tool calls       │
│  tools/*.rs       → handles each tool                │
│  store.rs         → reads/writes the graph           │
│  ontology.rs      → defines what types exist         │
│  namespaces.rs    → URL constants for RDF            │
│  util.rs          → generates IDs and timestamps     │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │ Oxigraph (in-memory RDF store)              │     │
│  │                                             │     │
│  │  Schema Graph    → ontology definition      │     │
│  │  Concepts Graph  → shared Skill, Concept... │     │
│  │  Links Graph     → cross-resource links     │     │
│  │  Resource Graphs → one per entity instance  │     │
│  │    graph/resource/uuid-1 → Stuart's data    │     │
│  │    graph/resource/uuid-2 → Memory Graph     │     │
│  │    graph/resource/uuid-3 → Rust             │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  On shutdown → dumps everything to graph.nq file     │
│  On startup  → loads graph.nq back into memory       │
└──────────────────────────────────────────────────────┘
```

---

## Key Concepts You Need First

### RDF (Resource Description Framework)

RDF stores data as **triples**: `subject → predicate → object`.

```
Stuart  →  hasEmail  →  "stuart@test.com"
Stuart  →  hasRole   →  "Developer"
Stuart  →  rdf:type  →  Person
```

Every subject and predicate is a **URL** (called an IRI). Objects can be URLs or literal values (strings, numbers, dates).

### Quads (Triples + Graph)

A **quad** is a triple with a fourth element: which **graph** it belongs to.

```
(Stuart, hasEmail, "stuart@test.com", graph:stuart-uuid)
(Stuart, rdf:type, Person,            graph:stuart-uuid)
```

This is how we give each person/project their own separate graph — the fourth element says "this fact lives in Stuart's graph".

### Named Nodes vs Literals

- **NamedNode**: A URL identifier, like `https://memory.claude.local/ontology#Person`
- **Literal**: A plain value, like `"Stuart"` or `"2026-03-26T12:00:00Z"`

### SPARQL

A query language for RDF data. Think SQL but for graphs:

```sparql
SELECT ?name WHERE {
    GRAPH ?g {
        ?person rdf:type mem:Person .
        ?person mem:name ?name .
    }
}
```

This says: "find anything that's a Person, and give me their name."

### MCP (Model Context Protocol)

A protocol for Claude to talk to external tools. Messages are JSON-RPC over stdin/stdout:

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
    "name": "memory_store_resource",
    "arguments": {"model": "Person", "properties": {"name": "Stuart"}}
}}
```

---

## File-by-File Walkthrough

### `Cargo.toml` — Project Configuration

```toml
oxigraph = { version = "0.5", default-features = false }
```

The `default-features = false` is crucial — it disables RocksDB (a C++ database engine that takes 10+ minutes to compile). We use Oxigraph's in-memory mode instead.

Key dependencies:
- **oxigraph**: The RDF database engine (stores and queries triples/quads)
- **rmcp**: The MCP server framework (handles JSON-RPC communication)
- **tokio**: Rust's async runtime (lets us handle I/O without blocking)
- **serde/serde_json**: Converts Rust structs to/from JSON
- **schemars**: Generates JSON Schema from Rust structs (so Claude knows what arguments each tool accepts)

---

### `src/main.rs` — Entry Point

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
```

`#[tokio::main]` is an attribute macro. It transforms `main` into an async function running on the Tokio runtime. Without it, you can't use `await`. Think of it as boilerplate that means "this program uses async I/O".

`anyhow::Result<()>` means "this function either succeeds (returns nothing) or fails with any kind of error". `anyhow` is a library that wraps all error types into one — convenient for `main()` where you just want to print the error and exit.

**What it does, step by step:**

1. **Sets up logging** — `tracing_subscriber` sends log messages to stderr (not stdout — stdout is reserved for MCP JSON messages)

2. **Finds the store path** — checks `MEMORY_GRAPH_PATH` env var, or defaults to `~/.claude/memory-graph/store`

3. **Opens the store** — `Arc::new(MemoryStore::open_or_create(...))` creates the graph database. `Arc` means "Atomic Reference Count" — it's how Rust safely shares data between the server and tool handlers. Multiple parts of the code hold a reference to the same store.

4. **Starts the MCP server** — `server.serve(rmcp::transport::stdio())` begins listening on stdin for JSON-RPC messages and responding on stdout

5. **Waits** — `service.waiting().await` keeps the program alive until the client disconnects

6. **Saves on shutdown** — `store.save()` dumps all in-memory data to the NQuads file

---

### `src/namespaces.rs` — URL Constants

RDF uses URLs as identifiers. Instead of writing full URLs everywhere, we define constants:

```rust
pub const MEM: &str = "https://memory.claude.local/ontology#";
```

So `mem:Person` in SPARQL really means `https://memory.claude.local/ontology#Person`.

**The graph IRIs** define where different types of data live:

| Constant | URL | What's stored there |
|----------|-----|-------------------|
| `GRAPH_SCHEMA` | `.../graph/schema` | The ontology definition (from base.ttl) |
| `GRAPH_LINKS` | `.../graph/links` | Cross-resource relationships |
| `GRAPH_CONCEPTS` | `.../graph/concepts` | Shared concept nodes (Skill, Concept, etc.) |
| `GRAPH_RESOURCE_BASE` | `.../graph/resource/` | Prefix for per-resource graphs (+ UUID) |

**Helper functions:**

- `named_node("https://...#", "Person")` → creates the URL `https://...#Person` as an RDF NamedNode
- `graph_node("https://...")` → same but for graph identifiers
- `resource_graph_iri("some-uuid")` → creates `https://memory.claude.local/graph/resource/some-uuid`

---

### `src/ontology.rs` — Type Definitions

This file defines what's allowed in the system. No RDF here — just plain Rust arrays and functions.

**Resource models** — entity types that get their own graph:

```rust
pub const RESOURCE_MODELS: &[&str] = &[
    "Person", "Project", "Company", "Task",
    "Technology", "Decision", "Pattern",
];
```

**Concept types** — lightweight shared nodes:

```rust
pub const CONCEPT_TYPES: &[&str] = &[
    "Skill", "Concept", "Constraint", "Preference",
];
```

**`scalar_properties(model)`** — returns which key-value properties each model allows:

```rust
"Person" => Some(&["name", "email", "role", "address", "description"]),
"Project" => Some(&["name", "projectType", "startDate", "status", ...]),
```

This is the "hybrid" part of the design. These scalar properties are stored directly on the resource (fast, flat). Relationships to other resources and concepts go through the links graph (traversable, shared).

**`name_property(type_name)`** — most types use `"name"` as their primary identifier, but concepts use `"label"`:

```rust
"Skill" | "Concept" | "Constraint" | "Preference" => "label",
_ => "name",
```

---

### `src/util.rs` — ID and Timestamp Helpers

```rust
pub fn new_resource_iri() -> (String, NamedNode) {
    let id = Uuid::new_v4().to_string();
    let iri = NamedNode::new(format!("{MEM}resource/{id}")).expect("Invalid IRI");
    (id, iri)
}
```

Every resource gets a UUID-based URL like `https://memory.claude.local/ontology#resource/a4a74ed0-...`. The function returns both the UUID string (used to find the resource's graph) and the full NamedNode (used in RDF triples).

`now_literal()` creates a timestamp literal like `"2026-03-26T12:00:00Z"^^xsd:dateTime`. The `^^xsd:dateTime` part tells RDF "this string is a dateTime, not just text".

---

### `src/store.rs` — The Core Engine

This is the largest file (~825 lines) and the heart of the system. Let's go section by section.

#### Error Types (lines 14-32)

```rust
#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("Oxigraph store error: {0}")]
    Store(#[from] oxigraph::store::StorageError),
    // ...
}
```

**Rust pattern: Error enum.** In Rust, errors are values, not exceptions. `StoreError` lists every kind of error that can happen. The `#[from]` attribute means "automatically convert this library error into my StoreError". So when Oxigraph returns a `StorageError`, the `?` operator converts it to a `StoreError::Store(...)`.

The `?` operator is everywhere in this code. It means: "if this returned an error, return that error immediately from this function. Otherwise, unwrap the success value." It's like a concise try/catch:

```rust
// This:
let store = Store::new()?;

// Is shorthand for:
let store = match Store::new() {
    Ok(s) => s,
    Err(e) => return Err(StoreError::from(e)),
};
```

#### The MemoryStore Struct (lines 34-37)

```rust
pub struct MemoryStore {
    store: Store,          // Oxigraph's in-memory RDF database
    data_path: Option<PathBuf>,  // Where to save on disk (None = don't persist)
}
```

`Option<PathBuf>` means "there might or might not be a file path". `Some("/path/to/file")` or `None`. This is how Rust handles nullable values — there's no `null`.

#### Opening/Creating the Store (lines 39-59)

```rust
pub fn open_or_create(data_dir: PathBuf) -> Result<Self, StoreError> {
```

`Result<Self, StoreError>` means this function returns either a `MemoryStore` or a `StoreError`. `Self` refers to the type we're implementing methods on (MemoryStore).

The flow:
1. Create the directory if it doesn't exist
2. Create a new in-memory Oxigraph store
3. If a `graph.nq` file exists from a previous session, load it
4. Load the base ontology (from `base.ttl`, compiled into the binary)

`include_str!("../ontology/base.ttl")` is a compile-time macro — it reads the file at build time and embeds the text into the binary. So the ontology is always available, even without the file on disk.

#### Saving to Disk (lines 72-90)

```rust
pub fn save(&self) -> Result<(), StoreError> {
    let Some(path) = &self.data_path else {
        return Ok(());  // No path = nothing to save
    };
```

`let Some(path) = ... else { return Ok(()); }` is a pattern match. If `self.data_path` is `None`, exit early. Otherwise, bind the inner value to `path`.

The save function iterates over every quad in the store and writes it to an **NQuads** file. NQuads is a plain-text format:

```
<subject> <predicate> "object" <graph> .
<subject> <predicate> "object" <graph> .
```

One line per fact. Simple, human-readable, easy to debug.

#### Creating a Resource (lines 117-170)

This is where a new entity (Person, Project, etc.) gets its own graph. Let's trace through creating Person "Stuart":

```rust
pub fn create_resource(
    &self,                              // borrows self (the store)
    model: &str,                        // "Person"
    properties: &HashMap<String, String>, // {"name": "Stuart", "email": "stuart@test.com"}
) -> Result<(String, NamedNode), StoreError> {
```

**`&self`** — Rust's borrow system. The `&` means "I'm borrowing the store, not taking ownership". Other code can still use the store after this call.

Step by step:
1. **Validate** the model is known (`ontology::is_resource_model("Person")` → true)
2. **Generate IDs** — a UUID like `a4a74ed0-...` and a NamedNode URL
3. **Create the graph IRI** — `graph/resource/a4a74ed0-...`
4. **Build quads** — the facts that go into this resource's graph:
   ```
   (resource:a4a7..., rdf:type, mem:Person, graph:a4a7...)
   (resource:a4a7..., mem:createdAt, "2026-03-26T...", graph:a4a7...)
   (resource:a4a7..., mem:updatedAt, "2026-03-26T...", graph:a4a7...)
   (resource:a4a7..., mem:name, "Stuart", graph:a4a7...)
   (resource:a4a7..., mem:email, "stuart@test.com", graph:a4a7...)
   ```
5. **Insert** each quad into the Oxigraph store

The `.clone()` calls you see everywhere are because Rust has strict ownership. When you put a NamedNode into a Quad, the Quad takes ownership. If you need to use that NamedNode again, you clone it first (make a copy). This is a common Rust pattern.

#### Finding a Resource (lines 241-276)

Uses SPARQL to search across all resource graphs:

```sparql
SELECT ?node ?g WHERE {
    GRAPH ?g {
        ?node rdf:type mem:Person .
        ?node mem:name "Stuart" .
    }
    FILTER(STRSTARTS(STR(?g), "https://memory.claude.local/graph/resource/"))
} LIMIT 1
```

This says: "Find a node that's a Person named Stuart, in any graph that starts with our resource prefix. Give me the node and which graph it's in."

The `FILTER(STRSTARTS(...))` ensures we only search resource graphs, not the schema or links graph.

**The match block** (lines 258-275) extracts the results:

```rust
match self.query(&sparql)? {
    QueryResults::Solutions(mut solutions) => {
        if let Some(Ok(solution)) = solutions.next() {
            if let (Some(Term::NamedNode(iri)), Some(Term::NamedNode(graph))) =
                (solution.get("node"), solution.get("g"))
            {
```

This is Rust's pattern matching — it's checking:
1. Did the query return solutions (not a boolean or graph)?
2. Is there at least one solution?
3. Are both `?node` and `?g` NamedNodes (not literals)?

If all three conditions pass, we extract the IRI and graph ID.

#### Cross-Links (lines 440-606)

Links live in a dedicated `links` graph. Each link is its own node with properties:

```
(link:uuid, rdf:type, CrossLink, graph:links)
(link:uuid, linkSource, resource:stuart, graph:links)
(link:uuid, linkTarget, resource:memory-graph, graph:links)
(link:uuid, linkRelation, "worksOn", graph:links)
(link:uuid, linkCreatedAt, "2026-03-26T...", graph:links)
```

This is the **Arches ResourceXResource pattern** — links are separate from the resources they connect, so each resource's graph stays self-contained.

`get_links_for()` finds all links where a resource is either the source or target:

```sparql
FILTER(?source = <resource:stuart> || ?target = <resource:stuart>)
```

#### Recall — The Key Feature (lines 615-703)

This is what makes the graph more useful than flat files. Starting from one resource, it traverses outward to find connected context.

**Depth 1**: Stuart → (worksOn) → Memory Graph

**Depth 2**: Stuart → (worksOn) → Memory Graph → (uses) → Rust

The algorithm:
1. Get the starting resource's properties
2. Find all links to/from this resource (`get_links_for`)
3. For each linked resource, get its properties
4. If depth > 1, repeat step 2-3 for each linked resource (but skip back to the starting resource to avoid loops)
5. Tag second-hop results with "via Memory Graph" so the LLM knows the path

The `direction` field tells you which way the link goes:
- `"outgoing"` — this resource is the source (Stuart → worksOn → Memory Graph)
- `"incoming"` — this resource is the target (some other resource points here)
- `"via Memory Graph"` — found through a second hop

---

### `src/tools/mod.rs` — MCP Tool Router

This file defines the server that Claude talks to. It has two parts:

**1. Parameter structs** — define what arguments each tool accepts:

```rust
#[derive(Debug, Deserialize, JsonSchema)]
pub struct StoreResourceParams {
    pub model: String,
    pub properties: HashMap<String, String>,
}
```

The `#[derive(...)]` line auto-generates code:
- `Debug` — lets you print the struct for debugging
- `Deserialize` — serde can convert JSON into this struct
- `JsonSchema` — schemars can generate a JSON Schema, which tells Claude what arguments are valid

**2. Tool implementations** — the `#[tool_router]` macro generates the routing code:

```rust
#[tool(
    name = "memory_store_resource",
    description = "Create or update a resource instance..."
)]
async fn memory_store_resource(
    &self,
    params: Parameters<StoreResourceParams>,
) -> Result<CallToolResult, McpError> {
    let p = params.0;
    store_resource::handle_resource(&self.store, p.model, p.properties)
        .map_err(|e| McpError::internal_error(e.to_string(), None))
}
```

When Claude calls `memory_store_resource`, the MCP framework:
1. Deserializes the JSON arguments into `StoreResourceParams`
2. Calls this function
3. The function delegates to `store_resource::handle_resource`
4. `.map_err(...)` converts any `StoreError` into an MCP error response

The `#[tool_handler]` block at the bottom defines the server metadata — the name, description, and capabilities that Claude sees when it first connects.

---

### `src/tools/store_resource.rs` — Creating Resources

Two functions:

**`handle_resource`** — creates or updates a resource:
1. Extracts the `name` from properties (using `name_property` to know if it's `"name"` or `"label"`)
2. Tries to find an existing resource with that model+name
3. If found → update its properties
4. If not found → create a new resource with its own graph

**`handle_concept`** — creates a concept node:
- Simpler — just calls `store.store_concept()` which handles deduplication (if a concept with that label already exists, it returns the existing one)

---

### `src/tools/link.rs` — Connecting Resources

**`handle_link`** — creates a relationship between two resources:
1. Looks up both resources by model+name using `find_any()` (checks resources first, then concepts)
2. Creates a CrossLink in the links graph with source, target, relation, and metadata

**`handle_unlink`** — removes a relationship:
1. Looks up both resources
2. Finds the matching CrossLink and removes all its quads

**`find_any`** — a helper that searches for either a resource or a concept:
```rust
fn find_any(store: &MemoryStore, model: &str, name: &str) -> Result<NamedNode, StoreError> {
    if let Some((_, iri)) = store.find_resource(model, name)? {
        return Ok(iri);
    }
    if let Some(iri) = store.find_concept(model, name)? {
        return Ok(iri);
    }
    Err(StoreError::Other(format!("not found...")))
}
```

---

### `src/tools/recall.rs` — Context Retrieval

The most important tool for the LLM. Calls `store.recall()` and formats the result as JSON:

```json
{
    "iri": "https://memory.claude.local/ontology#resource/...",
    "model": "Person",
    "properties": {"name": "Stuart", "email": "stuart@test.com", "role": "Developer"},
    "linked_resources": [
        {
            "model": "Project",
            "relation": "worksOn",
            "direction": "outgoing",
            "properties": {"name": "Memory Graph", "status": "prototype"}
        },
        {
            "model": "Technology",
            "relation": "uses",
            "direction": "via Memory Graph",
            "properties": {"name": "Rust", "category": "language"}
        }
    ]
}
```

The `depth` parameter controls how many hops to traverse:
- `depth: 1` → direct links only
- `depth: 2` → includes resources linked to the linked resources

---

### `src/tools/query.rs` — Raw SPARQL

Passes SPARQL directly to the store for power users. Returns:
- **SELECT** → JSON array of results
- **CONSTRUCT** → N-Triples (raw RDF)
- **ASK** → `"true"` or `"false"`

---

### `src/tools/forget.rs` — Soft Delete

Marks a resource as invalidated by adding three properties to its graph:
- `invalidated = true`
- `invalidatedAt = (timestamp)`
- `invalidationReason = (the reason)`

The original data is preserved — nothing is deleted. This is important for provenance ("why did we remove this?").

---

### `src/tools/reflect.rs` — Diagnostics

Generates a report showing:
- Resource counts by model (how many Persons, Projects, etc.)
- Concept counts by type
- Cross-link counts by relation type
- Recently added resources

Uses SPARQL aggregate queries (`COUNT`, `GROUP BY`) across the different graphs.

---

### `ontology/base.ttl` — The Schema

Written in **Turtle** format (a human-readable RDF syntax). Defines:

1. **Resource model classes** — what types of entities exist (Person, Project, etc.)
2. **Concept type classes** — what types of shared nodes exist (Skill, Concept, etc.)
3. **Properties** — what attributes each type can have
4. **Relationship types** — what kinds of links are valid (worksOn, uses, etc.)
5. **CrossLink class** — the structure of cross-graph links

This file is loaded into the `schema` graph on first startup. It's documentation for the system — the code in `ontology.rs` is what actually enforces the rules.

---

## Data Flow: What Happens When...

### "Create Person named Stuart with email stuart@test.com"

```
Claude sends:
  {"method": "tools/call", "params": {"name": "memory_store_resource",
   "arguments": {"model": "Person", "properties": {"name": "Stuart", "email": "stuart@test.com"}}}}

  → mod.rs receives, deserializes into StoreResourceParams
  → calls store_resource::handle_resource()
  → extracts name "Stuart" from properties
  → calls store.find_resource("Person", "Stuart") → None (doesn't exist yet)
  → calls store.create_resource("Person", {"name": "Stuart", "email": "stuart@test.com"})
    → generates UUID: a4a74ed0-...
    → creates graph IRI: graph/resource/a4a74ed0-...
    → inserts 5 quads into that graph:
        (resource:a4a7, rdf:type, Person)
        (resource:a4a7, createdAt, "2026-03-26T...")
        (resource:a4a7, updatedAt, "2026-03-26T...")
        (resource:a4a7, name, "Stuart")
        (resource:a4a7, email, "stuart@test.com")
  → returns success message with IRI and graph

Claude receives:
  "Created Person 'Stuart'\nIRI: .../resource/a4a74ed0-...\nGraph: .../graph/resource/a4a74ed0-..."
```

### "Link Stuart worksOn Memory Graph"

```
Claude sends:
  {"method": "tools/call", "params": {"name": "memory_link",
   "arguments": {"source_model": "Person", "source_name": "Stuart",
                  "target_model": "Project", "target_name": "Memory Graph",
                  "relation": "worksOn"}}}

  → mod.rs receives, deserializes into LinkParams
  → calls link::handle_link()
  → find_any("Person", "Stuart") → finds resource:a4a7...
  → find_any("Project", "Memory Graph") → finds resource:d435...
  → calls store.create_link(source, target, "worksOn", {})
    → generates link UUID: 31bd269a-...
    → inserts 5 quads into the links graph:
        (link:31bd, rdf:type, CrossLink)
        (link:31bd, linkSource, resource:a4a7)
        (link:31bd, linkTarget, resource:d435)
        (link:31bd, linkRelation, "worksOn")
        (link:31bd, linkCreatedAt, "2026-03-26T...")
  → returns success message
```

### "Recall Stuart with depth 2"

```
Claude sends:
  {"method": "tools/call", "params": {"name": "memory_recall",
   "arguments": {"model": "Person", "name": "Stuart", "depth": 2}}}

  → find_resource("Person", "Stuart") → (graph_id: "a4a7...", iri: resource:a4a7)
  → recall(iri, graph_id, depth=2)

    Step 1: Get Stuart's properties
      → {"name": "Stuart", "email": "stuart@test.com", "role": "Developer"}

    Step 2: Get all links involving Stuart
      → SPARQL finds: link where source=Stuart, target=Memory Graph, relation=worksOn

    Step 3: For each link, get the other resource's properties
      → Memory Graph: {"name": "Memory Graph", "projectType": "code", "status": "prototype"}

    Step 4: depth > 1, so check Memory Graph's links too
      → SPARQL finds: link where source=Memory Graph, target=Rust, relation=uses
      → Skip any links back to Stuart (avoid loops)
      → Rust: {"name": "Rust", "category": "language", "version": "2021"}
      → Tagged as direction: "via Memory Graph"

    Step 5: Combine and return JSON

  → Claude receives the full context tree
```

---

## Rust Patterns Used

### `Result<T, E>` and the `?` Operator

Nearly every function returns `Result`. The `?` propagates errors:

```rust
let store = Store::new()?;  // If this fails, return the error
let data = std::fs::read_to_string(&path)?;  // Same here
```

### `Option<T>` — Nullable Values

Rust has no `null`. Instead, `Option<String>` is either `Some("value")` or `None`:

```rust
pub fn find_resource(...) -> Result<Option<(String, NamedNode)>, StoreError> {
    // Returns Ok(Some(...)) if found, Ok(None) if not found, Err(...) if error
}
```

### `&self` vs `self` — Borrowing

- `&self` — borrows the struct (read access, struct still usable after)
- `&mut self` — mutable borrow (write access, exclusive)
- `self` — takes ownership (struct consumed, can't use after)

All our methods use `&self` because Oxigraph handles its own internal mutability.

### `.clone()` — Copying Values

Rust's ownership system means each value has one owner. When you need the same value in two places:

```rust
Quad::new(iri.clone(), predicate, value, graph.clone())
//        ^^^ clone because iri is used again later
```

### Pattern Matching

```rust
match &quad.object {
    Term::Literal(lit) => { /* it's a string value */ }
    Term::NamedNode(nn) => { /* it's a URL reference */ }
    _ => { /* something else, ignore */ }
}
```

### `if let` — Conditional Destructuring

```rust
if let Some((graph_id, iri)) = store.find_resource("Person", "Stuart")? {
    // Found it — graph_id and iri are now available
} else {
    // Not found
}
```

### Closures (Anonymous Functions)

```rust
.map_err(|e| StoreError::Other(e.to_string()))
//       ^^^ closure: takes error `e`, converts to StoreError
```

### Iterators and Collect

```rust
let old_quads: Vec<_> = self.store
    .quads_for_pattern(...)     // returns an iterator
    .collect::<Result<Vec<_>, _>>()?;  // collects into a Vec, propagating errors
```

---

## SPARQL Queries Explained

The system uses SPARQL in several places. Here are the main queries:

### Find a resource by model and name

```sparql
SELECT ?node ?g WHERE {
    GRAPH ?g {
        ?node rdf:type mem:Person .      -- must be a Person
        ?node mem:name "Stuart" .         -- named "Stuart"
    }
    FILTER(STRSTARTS(STR(?g), "https://memory.claude.local/graph/resource/"))
                                          -- only in resource graphs
} LIMIT 1
```

### Find all links for a resource

```sparql
SELECT ?link ?source ?target ?relation WHERE {
    GRAPH <https://memory.claude.local/graph/links> {
        ?link rdf:type mem:CrossLink .
        ?link mem:linkSource ?source .
        ?link mem:linkTarget ?target .
        ?link mem:linkRelation ?relation .
        FILTER(?source = <resource:a4a7...> || ?target = <resource:a4a7...>)
    }
}
```

### Count resources by type (reflect)

```sparql
SELECT ?type (COUNT(DISTINCT ?node) as ?count) WHERE {
    GRAPH ?g {
        ?node rdf:type ?type .
    }
    FILTER(STRSTARTS(STR(?g), "https://memory.claude.local/graph/resource/"))
} GROUP BY ?type ORDER BY DESC(?count)
```

---

## How to Run and Test

### Build

```bash
cargo build          # Debug build (~7 seconds)
cargo build --release  # Optimised build
```

### Run

```bash
# Default store location: ~/.claude/memory-graph/store
cargo run

# Custom location
MEMORY_GRAPH_PATH=/tmp/test-store cargo run

# With debug logging
RUST_LOG=debug cargo run
```

The server reads JSON-RPC from stdin and writes responses to stdout. Logs go to stderr.

### Test with manual JSON-RPC

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | cargo run 2>/dev/null
```

### Use with Claude Code

Add to your Claude Code MCP settings:

```json
{
    "mcpServers": {
        "memory-graph": {
            "command": "/path/to/claude-memory-graph",
            "env": {
                "MEMORY_GRAPH_PATH": "/path/to/store"
            }
        }
    }
}
```

### Inspect stored data

The store persists to `graph.nq` in the store directory. You can read it directly:

```bash
cat ~/.claude/memory-graph/store/graph.nq
```

Each line is one quad: `<subject> <predicate> <object> <graph> .`
