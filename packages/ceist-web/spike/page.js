// The spike page: Rós Madair (wasm) + duckdb-wasm over the demo snapshot, and bge-small in onnxruntime-web.
import * as duckdb from '@duckdb/duckdb-wasm';
import * as ort from 'onnxruntime-web/wasm';
import { Tokenizer } from '@huggingface/tokenizers';
import init, { Compiler } from './rm-wasm/ros_madair_wasm.js';

const DUCK = '/node_modules/@duckdb/duckdb-wasm/dist/';
const MODELS = ['Figure', 'Group', 'Monument', 'Object', 'Site', 'Tale'];
// the views the native Python Reader registers over a snapshot dir, by file prefix
const VIEWS = {
  tiles: 'tiles_', edges: 'edges_', edges_rev: 'redges_', concept_index: 'concepts_',
  ordered_index: 'ordered_', grid: 'grid_', resources: 'resources_', concepts: 'concept_catalog',
};

const timed = async (times, key, fn) => {
  const t = performance.now();
  const out = await fn();
  times[key] = Math.round(performance.now() - t);
  return out;
};

async function sha256(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function openDuck(times) {
  const manifest = await (await fetch('/snapshot/manifest.json')).json();
  const db = await timed(times, 'duckdb_init', async () => {
    const worker = new Worker(DUCK + 'duckdb-browser-eh.worker.js');
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(DUCK + 'duckdb-eh.wasm');
    return db;
  });
  const conn = await timed(times, 'snapshot_register', async () => {
    const names = manifest.artifacts.map((a) => a.path);
    await Promise.all(names.map(async (name) => {
      const buf = new Uint8Array(await (await fetch('/snapshot/' + name)).arrayBuffer());
      await db.registerFileBuffer(name, buf);
    }));
    const conn = await db.connect();
    for (const [view, prefix] of Object.entries(VIEWS)) {
      const files = names.filter((n) => n.startsWith(prefix)).map((n) => `'${n}'`);
      await conn.query(`CREATE VIEW ${view} AS SELECT * FROM read_parquet([${files.join(', ')}])`);
    }
    return conn;
  });
  return conn;
}

async function runQueries(conn, compiler, fixtures) {
  const results = [];
  for (const f of fixtures.queries) {
    for (const q of f.queries) {
      const t0 = performance.now();
      const sql = compiler.compile(JSON.stringify(q.ir), true, true, true, true, true, false);
      const compileMs = performance.now() - t0;
      const ordered = `SELECT resource_id FROM (${sql}) t ORDER BY resource_id`;
      const run = async () => (await conn.query(ordered)).getChildAt(0).toArray();
      const t1 = performance.now();
      const ids = await run();
      const firstMs = performance.now() - t1;
      const warm = [];
      for (let i = 0; i < 5; i++) {
        const t = performance.now();
        await run();
        warm.push(performance.now() - t);
      }
      warm.sort((a, b) => a - b);
      const hash = await sha256(ids.join('\n'));
      results.push({
        kind: f.kind, count: ids.length, expected: q.count, match: hash === q.sha256,
        compile_ms: +compileMs.toFixed(2), first_ms: Math.round(firstMs), warm_ms: Math.round(warm[2]),
        python_ms: q.python_ms,
      });
    }
  }
  return results;
}

async function embed(times, expected) {
  ort.env.wasm.wasmPaths = '/node_modules/onnxruntime-web/dist/';
  ort.env.wasm.numThreads = 1;
  const [session, tokenizer] = await timed(times, 'model_load', () => Promise.all([
    fetch('/model/model.onnx').then((r) => r.arrayBuffer())
      .then((buf) => ort.InferenceSession.create(new Uint8Array(buf), { executionProviders: ['wasm'] })),
    fetch('/model/tokenizer.json').then((r) => r.json()).then((json) => new Tokenizer(json, {})),
  ]));
  const run = async (text) => {
    const enc = tokenizer.encode(text);
    const n = enc.ids.length;
    const tensor = (xs) => new ort.Tensor('int64', BigInt64Array.from(xs, BigInt), [1, n]);
    const feeds = { input_ids: tensor(enc.ids), attention_mask: tensor(enc.attention_mask) };
    if (session.inputNames.includes('token_type_ids')) feeds.token_type_ids = tensor(new Array(n).fill(0));
    const hidden = (await session.run(feeds))[session.outputNames[0]].data;
    const cls = Array.from(hidden.slice(0, hidden.length / n));
    const norm = Math.hypot(...cls);
    return { ids: enc.ids, vec: cls.map((x) => x / norm) };
  };
  const first = await timed(times, 'embed_first', () => run(expected.phrase));
  await run('which tales feature Medb');
  const t = performance.now();
  for (let i = 0; i < 10; i++) await run(expected.phrase);
  const cosine = first.vec.reduce((s, x, i) => s + x * expected.vector[i], 0);
  return {
    cosine: +cosine.toFixed(5),
    token_ids_match: JSON.stringify(first.ids) === JSON.stringify(expected.token_ids),
    embed_warm_ms: +((performance.now() - t) / 10).toFixed(1),
  };
}

async function main() {
  const times = {};
  const t0 = performance.now();
  const swReady = 'serviceWorker' in navigator
    ? navigator.serviceWorker.register('/sw.js').then(() => navigator.serviceWorker.ready) : null;
  const fixtures = await (await fetch('/fixtures.json')).json();
  const [conn, compiler] = await Promise.all([
    openDuck(times),
    timed(times, 'ros_madair_init', async () => {
      await init({ module_or_path: '/rm-wasm/ros_madair_wasm_bg.wasm' });
      const graphs = await Promise.all(MODELS.map((m) => fetch(`/graphs/${m}.json`).then((r) => r.text())));
      return new Compiler(`[${graphs.join(',')}]`);
    }),
  ]);
  times.query_ready = Math.round(performance.now() - t0);
  const queries = await runQueries(conn, compiler, fixtures);
  const embedding = await embed(times, fixtures.embedding);
  times.total = Math.round(performance.now() - t0);
  if (swReady) await swReady;
  return { times, queries, embedding, controlled: !!navigator.serviceWorker?.controller };
}

window.spike = main().catch((e) => ({ error: String(e && e.stack || e) }));
