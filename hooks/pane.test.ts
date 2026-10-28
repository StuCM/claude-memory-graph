import { expect, test } from 'claude-code/testing'

const GRAPH_TOOL = 'mcp__plugin_memory-graph_memory-graph__memory_recall'
const CONTEXT_DIR = '/home/u/.claude/context'

type Reply = { output?: string; core?: Record<string, unknown>; state?: Record<string, unknown>; errors?: string[] }

// Hooks registered here stand for the engine beneath the plugin. `engine`
// answers the calls the mod makes on `$` and records them: the commands it
// registered, how often it opened the pane, and every Python request (the
// parsed stdin of each `hookrun` process). `reply` decides what Python says.
function engine(on: any, reply: (request: any) => Reply | 'crash' = () => ({ output: '' })) {
  const seen = { commands: [] as string[], opens: 0, python: [] as any[] }
  on('command.register', (_: any, e: any) => {
    seen.commands.push(e.name)
    return { value: { command: e.name } }
  })
  on('ui.open', () => {
    seen.opens += 1
    return { value: { isPlaced: true } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('session.cwd', () => ({ value: '/w/quartz' }))
  // The engine's own answer to each classic event: no settings hooks configured.
  for (const event of ['SessionStart', 'UserPromptSubmit', 'Stop', 'SessionEnd']) {
    on(`classic.${event}`, () => ({}))
  }
  const store = new Map<string, unknown>()
  on('store.get', (_: any, e: any) => ({ value: store.get(e.key) }))
  on('store.set', (_: any, e: any) => { store.set(e.key, e.value); return { value: undefined } })
  on('tool.call', () => ({ result: { content: [{ type: 'text', text: 'ok' }] } }))
  on('fs.exists', () => ({ value: true }))
  on('fs.read', () => ({ value: 'PROTOCOL' }))
  on('env.get', (_: any, e: any) => ({
    value: e.name === 'CLAUDE_CONTEXT_DIR' ? CONTEXT_DIR : e.name === 'HOME' ? '/home/u' : undefined,
  }))
  on('process.run', (_: any, e: any) => {
    if (e.argv[0] === 'grep') return { value: { exitCode: 1, stdout: '', stderr: '' } }
    const request = JSON.parse(e.init.stdin)
    seen.python.push(request)
    const answer = reply(request)
    if (answer === 'crash') return { value: { exitCode: 1, stdout: '', stderr: 'Traceback: boom' } }
    return { value: { exitCode: 0, stdout: JSON.stringify(answer), stderr: '' } }
  })
  return seen
}

async function start($: any) {
  await $.session.start({ cwd: '/w/quartz', surface: 'terminal', isInteractive: true })
}

// ---------------------------------------------------------------- pane modes

test('auto opens the pane on a graph tool call', { options: { pane: 'auto' } }, async ($, on) => {
  const seen = engine(on)
  await start($)
  await $.tool.call({ tool: GRAPH_TOOL, model: 'Decision', name: 'x' })
  expect(seen.commands).toContain('graph-panel')
  expect(seen.opens).toBe(1)
})

test('auto is the default', async ($, on) => {
  const seen = engine(on)
  await start($)
  await $.tool.call({ tool: GRAPH_TOOL, model: 'Decision', name: 'x' })
  expect(seen.opens).toBe(1)
})

test('manual keeps /graph-panel but never opens itself', { options: { pane: 'manual' } }, async ($, on) => {
  const seen = engine(on)
  await start($)
  await $.tool.call({ tool: GRAPH_TOOL, model: 'Decision', name: 'x' })
  expect(seen.commands).toContain('graph-panel')
  expect(seen.opens).toBe(0)
})

test('off drops the pane but memory still runs', { options: { pane: 'off' } }, async ($, on) => {
  const seen = engine(on, () => ({ output: 'Relevant memory' }))
  await start($)
  await $.tool.call({ tool: GRAPH_TOOL, model: 'Decision', name: 'x' })
  const result = await $.classic.UserPromptSubmit({ prompt: 'why pyoxigraph' })
  expect(seen.commands).toEqual([])
  expect(seen.opens).toBe(0)
  expect(result.additionalContext).toEqual(['Relevant memory'])
})

// ------------------------------------------------------- injection + state

test('a prompt injects what Python recalled and keeps the state it returns', async ($, on) => {
  const seen = engine(on, request => ({
    output: request.event === 'UserPromptSubmit' ? 'Memory entry points: X' : '',
    core: { prompt_count: (request.core.prompt_count ?? 0) + 1, project: 'quartz' },
    state: { 'memory-recall': { injected: ['g1'] } },
  }))
  await start($)
  const first = await $.classic.UserPromptSubmit({ prompt: 'why pyoxigraph' })
  expect(first.additionalContext).toEqual(['Memory entry points: X'])
  await $.classic.UserPromptSubmit({ prompt: 'and rdflib?' })
  // the second call carries what the first one returned
  const second = seen.python.filter(r => r.event === 'UserPromptSubmit')[1]
  expect(second.core.prompt_count).toBe(1)
  expect(second.state['memory-recall'].injected).toEqual(['g1'])
  expect(second.enabled).toEqual(['memory-recall', 'context-counter'])
})

test('session start injects the protocol and the prime', async ($, on) => {
  engine(on, request => ({ output: request.event === 'SessionStart' ? 'PRIME' : '' }))
  const result = await $.classic.SessionStart({ source: 'startup' })
  expect(result.additionalContext).toEqual(['PROTOCOL', 'PRIME'])
})

test('review is opt-in', { options: { review: true } }, async ($, on) => {
  const seen = engine(on)
  await $.classic.UserPromptSubmit({ prompt: 'hello there' })
  expect(seen.python[0].enabled).toContain('graph-review')
})

test('memory stays local unless a server is set', async ($, on) => {
  const seen = engine(on)
  await $.classic.UserPromptSubmit({ prompt: 'hello there' })
  expect(seen.python[0].remote).toBeUndefined()
})

test('a memory server reaches Python with its token', {
  options: { server: 'https://memory.example.com', server_token: 's3cret' },
}, async ($, on) => {
  const seen = engine(on)
  await $.classic.UserPromptSubmit({ prompt: 'hello there' })
  expect(seen.python[0].remote).toEqual({ url: 'https://memory.example.com', token: 's3cret', lookups: 'server' })
})

test('a local copy of the server graph is opt-in', {
  options: { server: 'https://memory.example.com', server_token: 's3cret', lookups: 'local copy' },
}, async ($, on) => {
  const seen = engine(on)
  await $.classic.UserPromptSubmit({ prompt: 'hello there' })
  expect(seen.python[0].remote.lookups).toBe('replica')
})

test('answer settings reach Python as gate keys', {
  options: { answer_questions: false, answer_max_rows: 3 },
}, async ($, on) => {
  const seen = engine(on)
  await $.classic.UserPromptSubmit({ prompt: 'which decisions affect quartz?' })
  expect(seen.python[0].gate).toEqual({
    ANSWER_QUESTIONS: false, ANSWER_MAX_QUESTIONS: 2, ANSWER_MAX_ROWS: 3, ANSWER_COVERAGE: 0.8,
  })
})

test('a Python failure fails open', async ($, on) => {
  engine(on, () => 'crash')
  const result = await $.classic.UserPromptSubmit({ prompt: 'why pyoxigraph' })
  expect(result.additionalContext ?? []).toEqual([])
})

// --------------------------------------------------------------------- Stop

test('Stop turns Python output into a block', async ($, on) => {
  engine(on, request => ({ output: request.event === 'Stop' ? '[context] 3 uncaptured' : '' }))
  const result = await $.classic.Stop({ stop_hook_active: false })
  expect(result.block).toBe('[context] 3 uncaptured')
})

test('a stop that follows a block is let through without asking Python', async ($, on) => {
  const seen = engine(on, () => ({ output: 'block again' }))
  const result = await $.classic.Stop({ stop_hook_active: true })
  expect(result.block).toBeUndefined()
  expect(seen.python).toEqual([])
})

// -------------------------------------------------------------- tool calls

test('digs are counted in-process, without starting Python', async ($, on) => {
  const seen = engine(on)
  await start($)
  await $.tool.call({ tool: 'Read', file_path: '/a.py' })
  await $.tool.call({ tool: 'Grep', pattern: 'x' })
  await $.tool.call({ tool: 'Bash', command: 'rg foo' })
  await $.tool.call({ tool: 'Bash', command: 'npm test' })      // not a dig
  expect(seen.python).toEqual([])
  await $.classic.Stop({ stop_hook_active: false })
  expect(seen.python[0].state['context-counter'].dig_count).toBe(3)
})

test('an explicit memory lookup is logged through Python', async ($, on) => {
  const seen = engine(on)
  await start($)
  await $.tool.call({ tool: GRAPH_TOOL, model: 'Decision', name: 'x' })
  const logged = seen.python.find(r => r.event === 'PostToolUse')
  expect(logged.payload.tool_name).toBe(GRAPH_TOOL)
  expect(logged.payload.tool_input).toEqual({ model: 'Decision', name: 'x' })
})

function realPaths(on: any, map: Record<string, string>) {
  on('fs.stat', (_: any, e: any) => {
    const real = map[e.path]
    return real ? { value: { isDirectory: true, realPath: real } } : { deny: 'ENOENT' }
  })
}

test('writes to the context log are approved; others fall through', async ($, on) => {
  engine(on)
  realPaths(on, { [CONTEXT_DIR]: CONTEXT_DIR, '/repo': '/repo' })
  on('tool.check', () => ({ decision: 'ask' }))
  const inside = await $.tool.check({ tool: 'Write', input: { file_path: `${CONTEXT_DIR}/quartz__x.md` } })
  const outside = await $.tool.check({ tool: 'Write', input: { file_path: '/repo/main.py' } })
  const bash = await $.tool.check({ tool: 'Bash', input: { command: `echo x >> ${CONTEXT_DIR}/f.md` } })
  expect(inside.decision).toBe('allow')
  expect(outside.decision).toBe('ask')
  expect(bash.decision).toBe('ask')
})

test('a symlink out of the context dir is not approved', async ($, on) => {
  engine(on)
  realPaths(on, { [CONTEXT_DIR]: CONTEXT_DIR, [`${CONTEXT_DIR}/link`]: '/etc' })
  on('tool.check', () => ({ decision: 'ask' }))
  const escaped = await $.tool.check({ tool: 'Write', input: { file_path: `${CONTEXT_DIR}/link/passwd` } })
  expect(escaped.decision).toBe('ask')
})

// ---------------------------------------------------------------- the pane

const PANE = {
  plugin: 'memory-graph', component: 'Pane', requestId: 'memory-graph',
  props: { title: 'Memory graph', isFocused: true, bodyColumns: 80, placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

test('the pane shows what was injected, on every surface', async ($, on) => {
  engine(on, request => ({ output: request.event === 'UserPromptSubmit' ? 'Memory entry points: Use pyoxigraph' : '' }))
  await start($)
  await $.classic.UserPromptSubmit({ prompt: 'why pyoxigraph' })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /Use pyoxigraph/ })).toBeDefined()
    await ui.unmount()
  }
})

test('the State tab shows counters and the last error', async ($, on) => {
  engine(on, () => 'crash')
  await start($)
  await $.classic.UserPromptSubmit({ prompt: 'why pyoxigraph' })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'tab-state' })
  expect(await ui.find({ type: 'Text', text: /uncaptured turns/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Traceback: boom/ })).toBeDefined()
  await ui.unmount()
})
