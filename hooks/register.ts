// The memory-graph mod: hook routing, session state, and the side pane.
//
// This replaced hook-kit (a Python dispatcher run as a fresh process per hook
// event, configured by hand in settings.json). The split now:
//
// - IN-PROCESS here, free: session state ($.state), dig counting on every
//   Read/Grep/Glob/Bash, auto-approving writes to the session context log,
//   compaction steering, and the pane.
// - ONE PYTHON CALL per prompt, per Stop, and at session start/end:
//   `python -m claude_memory_graph.hookrun`, stateless — state goes in on
//   stdin and comes back in the reply. Graph scoring, the context-file
//   cadence and the review stay in Python, where they are tested.
//
// Every Python failure fails open: no injection, no block, the error shown
// in the pane's State tab — a broken memory layer never breaks a session.

import { atom, read, update } from 'claude-code'
import type { Register, RenderNode } from 'claude-code'

import type { Decision, GraphCall, Injection, JsonObject, Session } from '../types'

const PLUGIN = 'memory-graph'
const PANE = 'memory-graph'
const TOOL_PREFIX = 'mcp__plugin_memory-graph_memory-graph__'
const MEMORY_TOOLS = new Set(['memory_recall', 'memory_query', 'memory_search'])
const MAX_CALLS = 50
const MAX_INJECTIONS = 40
const MAX_OUTPUT = 600
// File-inspection calls that make a turn a dig (mirrors gate/nudge.py).
const DIG_TOOLS = new Set(['Grep', 'Glob', 'Read'])
const DIG_BASH = /\b(rg|grep|find|fd|ag|cat|head|tail|tree|ls)\b/
const CONTEXT_WRITE_TOOLS = new Set(['Write', 'Edit', 'MultiEdit'])

// Tags change when a value's fields change: an earlier version's stored value
// is declined rather than misread after a reload.
const session = atom({ plugin: 'memory-graph', key: 'session' } as const,
  { core: {}, ext: {} } as Session, { shape: 'session-1' })
const calls = atom({ plugin: 'memory-graph', key: 'calls' } as const, [] as GraphCall[], { shape: 'calls-1' })
const injections = atom({ plugin: 'memory-graph', key: 'injections' } as const, [] as Injection[], { shape: 'injections-1' })
const decisions = atom({ plugin: 'memory-graph', key: 'decisions' } as const, [] as Decision[], { shape: 'decisions-1' })
const lastError = atom({ plugin: 'memory-graph', key: 'lastError' } as const, '')

type Options = { pane?: string; review?: boolean; server?: string; server_token?: string }
type Tab = 'injected' | 'state' | 'activity'
let tab: Tab = 'injected'

const isGraphTool = (tool: unknown): tool is string =>
  typeof tool === 'string' && tool.startsWith(TOOL_PREFIX)
const shortName = (tool: string) => tool.slice(TOOL_PREFIX.length).replace(/^memory_/, '')

function toolInput(e: Record<string, unknown>): JsonObject {
  const { tool: _t, tool_use_id: _id, agentId: _a, ...input } = e
  return input
}

function describeInput(input: JsonObject): string {
  const s = (v: unknown) => (typeof v === 'string' ? v : '')
  const props = input.properties as JsonObject | undefined
  if (input.source_name) return `${s(input.source_model)}/${s(input.source_name)} -${s(input.relation)}-> ${s(input.target_model)}/${s(input.target_name)}`
  if (props?.name) return `${s(input.model)}/${s(props.name)}`
  if (input.name) return `${s(input.model)}/${s(input.name)}`
  if (input.label) return `${s(input.concept_type)}/${s(input.label)}`
  return s(input.text) || s(input.query) || s(input.project)
}

// An MCP result is { content: [{ type: 'text', text }] }; anything else as JSON.
function textOf(output: unknown): string {
  if (typeof output === 'string') return output
  const content = (output as { content?: { text?: string }[] } | undefined)?.content
  if (Array.isArray(content)) return content.map(block => block.text ?? '').join('\n')
  return JSON.stringify(output ?? '')
}

function isDigCall(tool: string, input: JsonObject): boolean {
  if (DIG_TOOLS.has(tool)) return true
  return tool === 'Bash' && DIG_BASH.test(typeof input.command === 'string' ? input.command : '')
}

const now = () => new Date().toISOString().slice(11, 19)

// ---------------------------------------------------------------- python

type Reply = { output: string; core?: JsonObject; state?: Session['ext']; global?: Session['ext']; errors?: string[] }

// What every Python call carries besides the event: which extensions run, and
// the memory server when memory lives on one (docs/REMOTE.md).
type RunConfig = { enabled: string[]; remote?: { url: string; token: string } }

async function python($: any, event: string, payload: JsonObject, run: RunConfig): Promise<string> {
  const current = await read($, session)
  const global = ((await $.store.get('global')) ?? {}) as Session['ext']
  const request = JSON.stringify({ event, payload, core: current.core, state: current.ext, global, ...run })
  const root: string = $.plugin.root
  const venv = `${root}/.venv/bin/python`
  const viaUv = ['uv', 'run', '--quiet', '--project', root, 'python', '-m', 'claude_memory_graph.hookrun']
  // The venv is the fast path; uv re-syncs a missing or stale one (a plugin
  // update moves the code past what .venv has installed).
  const attempts = (await $.fs.exists(venv))
    ? [[venv, '-m', 'claude_memory_graph.hookrun'], viaUv]
    : [viaUv]
  let failure = ''
  for (const argv of attempts) {
    try {
      const { exitCode, stdout, stderr } = await $.process.run(argv, { stdin: request, timeoutMs: 60_000 })
      if (exitCode !== 0 || !stdout.trim()) {
        failure = `${argv[0]} exited ${exitCode}: ${String(stderr ?? '').slice(-300)}`
        continue
      }
      const reply = JSON.parse(stdout) as Reply
      await update($, session, s => ({ core: reply.core ?? s.core, ext: reply.state ?? s.ext }))
      if (reply.global) await $.store.set('global', reply.global)
      await update($, lastError, () => (reply.errors ?? []).join('\n'))
      return reply.output ?? ''
    } catch (err) {
      failure = `${argv[0]}: ${String(err)}`
    }
  }
  await update($, lastError, () => `${event}: ${failure}`)
  return ''
}

async function recordInjection($: any, event: string, text: string) {
  if (!text) return
  await update($, injections, list => [...list, { at: now(), event, text }].slice(-MAX_INJECTIONS))
  $.ui.invalidate('ui.render')
}

// grep, not $.fs.read: injections.jsonl outgrows fs.read's 4 MiB cap.
async function refreshDecisions($: any) {
  try {
    const home = (await $.env.get('MEMORY_GRAPH_STATE')) ?? (await $.env.get('CLAUDE_HOOK_KIT_HOME'))
      ?? `${await $.env.get('HOME')}/.claude/memory-graph/state`
    const id = await $.session.id()
    const { stdout } = await $.process.run(['grep', '-F', `"session": "${id}"`, `${home}/injections.jsonl`])
    const rows: Decision[] = []
    for (const line of String(stdout).split('\n')) {
      if (!line) continue
      try { rows.push(JSON.parse(line)) } catch { /* a line still being appended */ }
    }
    await update($, decisions, () => rows.slice(-MAX_INJECTIONS))
    $.ui.invalidate('ui.render')
  } catch { /* no log yet */ }
}

async function contextDir($: any): Promise<string> {
  return (await $.env.get('CLAUDE_CONTEXT_DIR')) ?? `${await $.env.get('HOME')}/.claude/context`
}

export const register: Register = (on, options) => {
  const opts = (options ?? {}) as Options
  const paneMode = opts.pane ?? 'auto'
  const server = String(opts.server ?? '').trim()
  const run: RunConfig = {
    enabled: ['memory-recall', 'context-counter', ...(opts.review ? ['graph-review'] : [])],
    ...(server ? { remote: { url: server, token: String(opts.server_token ?? '') } } : {}),
  }

  // --------------------------------------------------------- classic events

  on('classic.SessionStart', async ($, e, next) => {
    const result = await next(e)
    let protocol = ''
    try { protocol = await $.fs.read(`${$.plugin.root}/hooks/context-protocol.md`) } catch { /* fail open */ }
    const primed = await python($, 'SessionStart', e as unknown as JsonObject, run)
    await recordInjection($, 'session start', primed)
    const added = [protocol, primed].filter(Boolean)
    return added.length ? { ...result, additionalContext: [...(result.additionalContext ?? []), ...added] } : result
  })

  on('classic.UserPromptSubmit', async ($, e, next) => {
    const result = await next(e)
    const recalled = await python($, 'UserPromptSubmit', e as unknown as JsonObject, run)
    await recordInjection($, 'prompt', recalled)
    return recalled ? { ...result, additionalContext: [...(result.additionalContext ?? []), recalled] } : result
  })

  on('classic.Stop', async ($, e, next) => {
    const result = await next(e)
    // A stop that already follows a block lets the turn end: one block per
    // stop, never chained — the Python side checks the same flag.
    if (e.stop_hook_active) return result
    const reason = await python($, 'Stop', e as unknown as JsonObject, run)
    await refreshDecisions($)
    if (!reason) return result
    await recordInjection($, 'stop block', reason)
    return { ...result, block: result.block ? `${result.block}\n\n${reason}` : reason }
  })

  on('classic.SessionEnd', async ($, e, next) => {
    const result = await next(e)
    const note = await python($, 'SessionEnd', e as unknown as JsonObject, run)
    if (note) $.ui.toast(note)
    return result
  })

  // The classic PreCompact hook cannot reach the summary (it reads no
  // additionalContext); session.compact can — its instructions are what the
  // summariser is told.
  on('session.compact', async ($, e, next) => {
    if (e.trigger === 'precompute' || e.agentId) return next(e)
    const steer = await python($, 'PreCompact', { session_id: await $.session.id(), cwd: await $.session.cwd() }, run)
    if (!steer) return next(e)
    await recordInjection($, 'compaction', steer)
    return next({ ...e, instructions: e.instructions ? `${e.instructions}\n\n${steer}` : steer })
  })

  // ------------------------------------------------------------ tool calls

  // The protocol asks for a context-log append every few turns; a permission
  // prompt each time would stop the loop being used. Only Write/Edit whose
  // REAL path is inside the context dir — a symlink or ../ escape does not
  // count, and Bash is never covered. Everything else falls through.
  on('tool.check', async ($, e, next) => {
    if (!CONTEXT_WRITE_TOOLS.has(e.tool)) return next(e)
    const target = (e.input as JsonObject | undefined)?.file_path
    if (typeof target !== 'string' || !target) return next(e)
    try {
      const dir = (await $.fs.stat(await contextDir($), { resolve: true })).realPath
      const slash = target.lastIndexOf('/')
      const parent = (await $.fs.stat(target.slice(0, slash) || '/', { resolve: true })).realPath
      const real = `${parent}/${target.slice(slash + 1)}`
      if (dir && parent && (real === dir || real.startsWith(`${dir}/`)) && !target.slice(slash + 1).startsWith('..')) {
        return { decision: 'allow', reason: 'memory-graph: session context log' }
      }
    } catch { /* unresolvable: no decision */ }
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const input = toolInput(e as unknown as Record<string, unknown>)

    if (isDigCall(e.tool, input)) {
      // Counted here, in-process: this fires on every Read and Grep.
      await update($, session, s => {
        const counter = { ...(s.ext['context-counter'] ?? {}) }
        const turn = (s.core.prompt_count as number) ?? 0
        if (counter.dig_turn !== turn) { counter.dig_turn = turn; counter.dig_count = 0 }
        counter.dig_count = ((counter.dig_count as number) ?? 0) + 1
        return { ...s, ext: { ...s.ext, 'context-counter': counter } }
      })
      return next(e)
    }

    if (!isGraphTool(e.tool)) return next(e)
    const name = shortName(e.tool)
    const call: GraphCall = { id: e.tool_use_id, name, summary: describeInput(input), output: '', isErrored: false }
    await update($, calls, list => [call, ...list].slice(0, MAX_CALLS))
    if (paneMode === 'auto') await $.ui.open({ id: PANE, title: 'Memory graph' })
    const result = await next(e)
    const output = result.deny ?? textOf(result.result)
    await update($, calls, list => list.map(c => (c.id === call.id
      ? { ...c, output, isErrored: Boolean(result.deny || result.isError) } : c)))
    $.ui.invalidate('ui.render')
    if (MEMORY_TOOLS.has(e.tool.slice(TOOL_PREFIX.length))) {
      // An explicit recall is the miss detector's evidence; logging it needs
      // the state home, so it rides one Python call (rare: the model's own lookups).
      await python($, 'PostToolUse', {
        session_id: await $.session.id(), cwd: await $.session.cwd(),
        tool_name: e.tool, tool_input: input, tool_response: output,
      }, run)
    }
    return result
  })

  // -------------------------------------------------------------- the pane

  if (paneMode === 'off') return

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'graph-panel', description: 'Open the memory-graph pane', immediate: true })
    return next(e)
  })

  on('command.run', { command: 'graph-panel' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Memory graph', focus: true })
    await refreshDecisions($)
    return {}
  })

  on('turn.complete', async ($, e, next) => {
    await refreshDecisions($)
    return next(e)
  })

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (!isGraphTool(e.props.tool)) return next(e)
    const { Text } = $.ui.resolve(e)
    return Text({ dimColor: true, children: [`◆ graph ${shortName(e.props.tool)} ${describeInput(e.props.input as JsonObject)}`] })
  })

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (!isGraphTool(e.props.tool)) return next(e)
    const { Box } = $.ui.resolve(e)
    return Box({})
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const line = (text: string, extra: Record<string, unknown> = {}) => Text({ wrap: 'wrap', ...extra, children: [text] })
    const blank = () => Text({ children: [' '] })

    const tabButton = (name: Tab, label: string, hotkey: string) => Button({
      key: `tab-${name}`, label, hotkey, plain: true, dimColor: tab !== name,
      onPress: () => { tab = name; $.ui.invalidate('ui.render') },
    })

    let body: RenderNode[]
    if (tab === 'injected') {
      const injected = await read($, injections)
      const rows = await read($, decisions)
      const fired = rows.filter(r => r.fired).length
      body = [
        line('What reached the model this session', { bold: true }),
        ...(injected.length
          ? injected.slice().reverse().flatMap(i => [
              line(`${i.at}  ${i.event}`, { bold: true, dimColor: true }),
              line(i.text.length > 1500 ? `${i.text.slice(0, 1500)}…` : i.text),
            ])
          : [line('Nothing injected yet.', { dimColor: true })]),
        blank(),
        line(`Gate decisions: ${fired} fired of ${rows.length}`, { bold: true }),
        ...rows.slice().reverse().slice(0, 15).map(r => {
          if (r.kind === 'prime') return line(`prime  ${r.project ?? ''}`, { dimColor: true })
          if (r.kind === 'answer') return line(r.fired
            ? `answered ${r.rows ?? 0} rows  ${r.understood ?? r.q ?? ''}`
            : `unanswered  ${r.q ?? ''}`, { dimColor: !r.fired })
          const layer = r.kind === 'log' ? 'session log' : 'graph'
          const nodes = r.nodes?.length ? r.nodes.join(', ') : (r.top_node ?? '')
          const cluster = r.cluster ? ` +${r.cluster} similar` : ''
          return line(`${r.fired ? 'injected' : 'silent  '} ${layer} top ${r.top ?? 0} rest ${r.rest ?? 0}${cluster}  ${nodes}`,
            { dimColor: !r.fired })
        }),
      ]
    } else if (tab === 'state') {
      const s = await read($, session)
      const err = await read($, lastError)
      const core = s.core
      const counter = s.ext['context-counter'] ?? {}
      const significant = (core.significant_prompt_count as number) ?? 0
      const overdue = significant - ((counter.written_at as number) ?? 0)
      const digThisTurn = counter.dig_turn === core.prompt_count ? (counter.dig_count as number) ?? 0 : 0
      const memo = (s.ext['memory-recall']?.injected as unknown[] | undefined)?.length ?? 0
      body = [
        line(`project            ${core.project ?? '—'}`),
        line(`prompts            ${core.prompt_count ?? 0} (${significant} significant)`),
        line(`context tokens     ${core.context_tokens ?? '—'}`),
        blank(),
        line('Capture', { bold: true }),
        line(`uncaptured turns   ${overdue}  (Stop blocks at 3)`),
        line(`digs this turn     ${digThisTurn}  (trace asked at 8)`),
        blank(),
        line('Recall', { bold: true }),
        line(`memories injected  ${memo} distinct this session`),
        line(`settings           pane ${paneMode} · review ${opts.review ? 'on' : 'off'}`),
        line(`memory             ${server ? `server ${server} (local replica for recall)` : 'this machine'}`),
        ...(err ? [blank(), line('Last error', { bold: true, color: 'red' }), line(err, { color: 'red' })] : []),
      ]
    } else {
      const list = await read($, calls)
      body = list.length === 0
        ? [line('No graph calls yet.', { dimColor: true })]
        : list.map(call => Box({
            key: call.id, flexDirection: 'column', children: [
              Text({ bold: true, ...(call.isErrored && { color: 'red' }), children: [`${call.name}  ${call.summary}`] }),
              Text({ dimColor: true, wrap: 'wrap', children: [call.output.slice(0, MAX_OUTPUT) || '…running'] }),
            ],
          }))
    }

    return Box({
      flexDirection: 'column',
      children: [
        Box({ flexDirection: 'row', columnGap: 3, children: [
          tabButton('injected', 'Injected', '1'), tabButton('state', 'State', '2'), tabButton('activity', 'Activity', '3'),
        ] }),
        blank(),
        ...body,
      ],
    })
  })
}
