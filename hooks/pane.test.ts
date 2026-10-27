import { expect, test } from 'claude-code/testing'

const GRAPH_TOOL = 'mcp__plugin_memory-graph_memory-graph__memory_recall'

// Hooks registered here stand for the engine beneath the plugin, so they
// record what the plugin asked of it: which commands it registered and how
// often it opened the pane.
function engine(on: any) {
  const seen = { commands: [] as string[], opens: 0 }
  on('command.register', (_: any, e: any) => {
    seen.commands.push(e.name)
    return { value: { command: e.name } }
  })
  on('ui.open', () => {
    seen.opens += 1
    return { value: { isPlaced: true } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: { content: [{ type: 'text', text: 'ok' }] } }))
  return seen
}

async function graphCall($: any) {
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.tool.call({ tool: GRAPH_TOOL, model: 'Decision', name: 'x' })
}

test('auto opens the pane on a graph tool call', { options: { pane: 'auto' } }, async ($, on) => {
  const seen = engine(on)
  await graphCall($)
  expect(seen.commands).toContain('graph-panel')
  expect(seen.opens).toBe(1)
})

test('auto is the default', async ($, on) => {
  const seen = engine(on)
  await graphCall($)
  expect(seen.opens).toBe(1)
})

test('manual keeps /graph-panel but never opens itself', { options: { pane: 'manual' } }, async ($, on) => {
  const seen = engine(on)
  await graphCall($)
  expect(seen.commands).toContain('graph-panel')
  expect(seen.opens).toBe(0)
})

test('off registers nothing', { options: { pane: 'off' } }, async ($, on) => {
  const seen = engine(on)
  await graphCall($)
  expect(seen.commands).toEqual([])
  expect(seen.opens).toBe(0)
})
