// Side pane for memory-graph activity: graph tool calls draw there instead of
// in the transcript, alongside per-tool counts and what the recall hook did.
// Display only — the calls' output still reaches the model's context.
const PANE = 'memory-graph'
const TOOL_PREFIX = 'mcp__plugin_memory-graph_memory-graph__'
const MAX_CALLS = 50
const MAX_OUTPUT = 600

let tab = 'activity'
let calls = []
let counts = {}
let injections = []
let recalls = []

const isGraphTool = (tool) => typeof tool === 'string' && tool.startsWith(TOOL_PREFIX)
const shortName = (tool) => tool.slice(TOOL_PREFIX.length).replace(/^memory_/, '')

function describeInput(input) {
  if (!input || typeof input !== 'object') return ''
  if (input.source_name) return `${input.source_model}/${input.source_name} -${input.relation}-> ${input.target_model}/${input.target_name}`
  if (input.properties?.name) return `${input.model}/${input.properties.name}`
  if (input.name) return `${input.model}/${input.name}`
  if (input.label) return `${input.concept_type}/${input.label}`
  return input.text ?? input.query ?? input.project ?? ''
}

// An MCP result is { content: [{ type: 'text', text }] }; anything else is shown as JSON.
function textOf(output) {
  if (typeof output === 'string') return output
  if (Array.isArray(output?.content)) return output.content.map((block) => block.text ?? '').join('\n')
  return JSON.stringify(output ?? '')
}

// grep, not $.fs.read: injections.jsonl outgrows fs.read's 4 MiB cap.
async function readSessionLog($, name, session) {
  const home = (await $.env.get('CLAUDE_HOOK_KIT_HOME')) ?? `${await $.env.get('HOME')}/.claude/hook-kit`
  const { stdout } = await $.process.run(['grep', '-F', `"session": "${session}"`, `${home}/${name}`])
  const rows = []
  for (const line of stdout.split('\n')) {
    if (!line) continue
    try {
      rows.push(JSON.parse(line))
    } catch {
      // a line still being appended by the hook
    }
  }
  return rows
}

async function refreshLogs($) {
  const session = await $.session.id()
  injections = await readSessionLog($, 'injections.jsonl', session)
  recalls = await readSessionLog($, 'explicit-recalls.jsonl', session)
  $.ui.invalidate('ui.render')
}

function describeInjection(row) {
  if (row.kind === 'prime') return `prime  ${row.project}`
  const layer = row.kind === 'log' ? 'session log' : 'graph'
  const verdict = row.fired ? 'injected' : 'silent'
  const nodes = row.nodes?.length ? row.nodes.join(', ') : (row.top_node ?? '')
  return `${verdict} (${layer}, top ${row.top})  ${nodes}`
}

// options.pane (plugin.json userConfig, a /config picker):
//   auto   — the pane opens itself on the first graph tool call (default)
//   manual — only /graph-panel opens it
//   off    — register nothing: no pane, no command, and graph tool calls draw
//            in the transcript as normal (collapsing them with no pane to hold
//            the detail would hide their output everywhere)
export function register(on, options) {
  const mode = options?.pane ?? 'auto'
  if (mode === 'off') return

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'graph-panel', description: 'Open the memory-graph activity pane', immediate: true })
    return next(e)
  })

  on('command.run', { command: 'graph-panel' }, async ($) => {
    await $.ui.open({ id: PANE, title: 'Memory graph', focus: true })
    await refreshLogs($)
    return {}
  })

  on('tool.call', async ($, e, next) => {
    if (!isGraphTool(e.tool)) return next(e)
    const name = shortName(e.tool)
    counts[name] = (counts[name] ?? 0) + 1
    const call = { id: e.tool_use_id, name, summary: describeInput(e), output: '', isErrored: false }
    calls = [call, ...calls].slice(0, MAX_CALLS)
    // Opened by the mod itself, so it only places on a wide terminal.
    if (mode === 'auto') await $.ui.open({ id: PANE, title: 'Memory graph' })
    const result = await next(e)
    call.output = result.deny ?? textOf(result.result)
    call.isErrored = Boolean(result.deny || result.isError)
    $.ui.invalidate('ui.render')
    return result
  })

  on('turn.complete', async ($, e, next) => {
    await refreshLogs($)
    return next(e)
  })

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (!isGraphTool(e.props.tool)) return next(e)
    const { Text } = $.ui.resolve(e)
    return Text({ dimColor: true, children: [`◆ graph ${shortName(e.props.tool)} ${describeInput(e.props.input)}`] })
  })

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (!isGraphTool(e.props.tool)) return next(e)
    const { Box } = $.ui.resolve(e)
    return Box({})
  })

  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    const total = Object.values(counts).reduce((sum, n) => sum + n, 0)
    if (total === 0) return next(e)
    return next({ ...e, props: { ...e.props, suffix: `${e.props.suffix ?? ''} · graph ${total}` } })
  })

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== PANE) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)

    const tabButton = (name, label, hotkey) =>
      Button({
        key: 'tab-' + name,
        label,
        hotkey,
        plain: true,
        dimColor: tab !== name,
        onPress: () => {
          tab = name
          $.ui.invalidate('ui.render')
        },
      })

    let body
    if (tab === 'activity') {
      body = calls.length === 0
        ? [Text({ dimColor: true, children: ['No graph calls yet.'] })]
        : calls.map((call) =>
            Box({
              key: call.id,
              flexDirection: 'column',
              children: [
                Text({ bold: true, ...(call.isErrored && { color: 'red' }), children: [`${call.name}  ${call.summary}`] }),
                Text({ dimColor: true, wrap: 'wrap', children: [call.output.slice(0, MAX_OUTPUT) || '…running'] }),
              ],
            }),
          )
    } else if (tab === 'injected') {
      body = [
        Text({ bold: true, children: ['Recall hook'] }),
        ...(injections.length ? injections.map((row) => Text({ wrap: 'wrap', children: [describeInjection(row)] })) : [Text({ dimColor: true, children: ['Nothing yet.'] })]),
        Text({ children: [' '] }),
        Text({ bold: true, children: ['Explicit lookups'] }),
        ...(recalls.length ? recalls.map((row) => Text({ wrap: 'wrap', children: [`${row.found ? '✓' : '✗'} ${row.tool}  ${row.target}`] })) : [Text({ dimColor: true, children: ['Nothing yet.'] })]),
      ]
    } else {
      const fired = injections.filter((row) => row.fired).length
      body = [
        ...Object.entries(counts).map(([name, n]) => Text({ children: [`${name.padEnd(16)} ${n}`] })),
        Text({ children: [' '] }),
        Text({ children: [`recall hook fired ${fired} of ${injections.length} prompts`] }),
        Text({ children: [`explicit lookups ${recalls.length}`] }),
      ]
    }

    return Box({
      flexDirection: 'column',
      children: [
        Box({
          flexDirection: 'row',
          columnGap: 3,
          children: [tabButton('activity', 'Activity', '1'), tabButton('injected', 'Injected', '2'), tabButton('counts', 'Counts', '3')],
        }),
        Text({ children: [' '] }),
        ...body,
      ],
    })
  })
}
