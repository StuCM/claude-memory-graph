// Bundle the spike page, serve it, load it headless three times (cold, warm, offline) and print the table.
import { createServer } from 'node:http';
import { readFileSync, statSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { homedir } from 'node:os';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { chromium } from 'playwright';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const ASK = process.env.DEMO_ASK || '/home/stuart/git/personal/starches-demo/ask';
const MODEL = process.env.BGE_DIR || join(homedir(), '.cache/ceist/models/bge-small-en-v1.5');
const ROOTS = [
  ['/node_modules/', join(HERE, '../node_modules/')],
  ['/snapshot/', join(ASK, 'snapshot/')],
  ['/graphs/', join(ASK, 'data/graphs/')],
  ['/model/', MODEL + '/'],
  ['/', HERE],
];
const TYPES = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.wasm': 'application/wasm',
  '.json': 'application/json', '.html': 'text/html' };

await build({ entryPoints: [join(HERE, 'page.js')], bundle: true, format: 'esm', minify: true,
  outfile: join(HERE, 'bundle.js'), logLevel: 'warning' });

const served = new Map();
const server = createServer((req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname.replace(/^\/$/, '/index.html'));
  const [prefix, dir] = ROOTS.find(([p]) => path.startsWith(p));
  const file = join(dir, path.slice(prefix.length));
  try {
    const body = readFileSync(file);
    served.set(path, file);
    res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
const url = `http://127.0.0.1:${server.address().port}/`;

const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader'] });
const runs = {};
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on('pageerror', (e) => console.error('page error:', e.message));
  const load = async (name) => {
    await page.goto(url);
    runs[name] = await page.evaluate(() => window.spike);
    if (runs[name].error) throw new Error(`${name}: ${runs[name].error}`);
  };
  await load('cold');
  const coldServed = new Map(served);
  await load('warm');
  served.clear();
  await context.setOffline(true);
  await load('offline');
  report(coldServed);
} finally {
  await browser.close();
  server.close();
}

function category(path) {
  if (path.startsWith('/snapshot/')) return 'snapshot (parquet)';
  if (path.startsWith('/graphs/')) return 'model graphs (json)';
  if (path === '/model/model.onnx') return 'bge-small (onnx, quantised)';
  if (path.startsWith('/model/')) return 'tokenizer.json';
  if (path.endsWith('duckdb-eh.wasm')) return 'duckdb-wasm (wasm)';
  if (path.includes('/rm-wasm/') && path.endsWith('.wasm')) return 'ros-madair-wasm (wasm)';
  if (path.includes('onnxruntime-web') && path.endsWith('.wasm')) return 'onnxruntime-web (wasm)';
  if (path.endsWith('.js') || path.endsWith('.mjs')) return 'JS (page bundle, duckdb worker, glue)';
  return 'other';
}

function report(coldServed) {
  const sizes = {};
  for (const [path, file] of coldServed) {
    const s = (sizes[category(path)] ??= { raw: 0, gz: 0 });
    s.raw += statSync(file).size;
    s.gz += gzipSync(readFileSync(file)).length;
  }
  const mb = (n) => (n / 1e6).toFixed(2);
  console.log('\n| asset | bytes (MB) | gzip (MB) |\n|---|---|---|');
  let raw = 0, gz = 0;
  for (const [name, s] of Object.entries(sizes).sort((a, b) => b[1].raw - a[1].raw)) {
    console.log(`| ${name} | ${mb(s.raw)} | ${mb(s.gz)} |`);
    raw += s.raw; gz += s.gz;
  }
  console.log(`| **total** | ${mb(raw)} | ${mb(gz)} |`);

  console.log('\n| ms | cold | warm reload | offline reload |\n|---|---|---|---|');
  for (const key of Object.keys(runs.cold.times)) {
    console.log(`| ${key} | ${runs.cold.times[key]} | ${runs.warm.times[key]} | ${runs.offline.times[key]} |`);
  }
  console.log(`| embed (warm, per phrase) | ${runs.cold.embedding.embed_warm_ms} | ${runs.warm.embedding.embed_warm_ms} | ${runs.offline.embedding.embed_warm_ms} |`);

  console.log('\n| query | ids | match Python | compile ms | first ms | warm ms | Python ms |\n|---|---|---|---|---|---|---|');
  for (const q of runs.cold.queries) {
    console.log(`| ${q.kind} | ${q.count}/${q.expected} | ${q.match} | ${q.compile_ms} | ${q.first_ms} | ${q.warm_ms} | ${q.python_ms} |`);
  }
  const e = runs.offline.embedding;
  console.log(`\nembedding: cosine ${e.cosine}, token ids match ${e.token_ids_match}`);
  console.log(`offline reload: served by the network ${served.size} files, SW controlled ${runs.offline.controlled}`);
  const ok = Object.values(runs).every((r) => r.queries.every((q) => q.match) && r.embedding.cosine > 0.99)
    && served.size === 0;
  console.log(ok ? 'PASS' : 'FAIL');
  process.exitCode = ok ? 0 : 1;
}
