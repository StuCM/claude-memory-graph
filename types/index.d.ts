// State contract for the memory-graph mod (hooks/register.ts). Values here
// live in the session's $.state and survive a mod reload — a change of the
// pane setting in /config reloads the module mid-session, and the capture
// cadence must not reset when it does.

/** Free-form JSON object: the Python side owns the fields. */
export type JsonObject = { [key: string]: unknown }

/** What the mod hands Python with every call, and stores what comes back. */
export type Session = {
  /** Framework counters advanced by Python (prompt counts, project, tokens). */
  core: JsonObject
  /** Per-extension session dicts, keyed by extension name. */
  ext: { [name: string]: JsonObject }
}

/** A memory-graph tool call, for the pane's Activity tab. */
export type GraphCall = {
  id: string
  name: string
  summary: string
  output: string
  isErrored: boolean
}

/** Something the mod put in front of the model, for the Injected tab. */
export type Injection = {
  at: string
  event: string
  text: string
}

/** One gate decision line from injections.jsonl (fired or silent). */
export type Decision = {
  kind?: string
  fired?: boolean
  top?: number
  rest?: number
  nodes?: string[]
  top_node?: string
  cluster?: number
  project?: string
  q?: string
  understood?: string | null
  rows?: number
}

declare module 'claude-code' {
  interface PluginState {
    'memory-graph': {
      session: Shaped<Session>
      calls: Shaped<GraphCall[]>
      injections: Shaped<Injection[]>
      decisions: Shaped<Decision[]>
      lastError: string
    }
  }
}
