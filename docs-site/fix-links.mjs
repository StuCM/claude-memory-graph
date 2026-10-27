// Post-build: the docs link to each other and to code with repo-relative paths
// (so they work on GitHub). Blume resolves same-folder .md links; this resolves
// the rest — other doc folders to their site route, everything else in the repo
// to its GitHub page. Runs over dist/ after `blume build`.
import { readdirSync, readFileSync, writeFileSync, existsSync, statSync } from "node:fs";
import { join, dirname, relative, resolve, posix } from "node:path";

const repo = resolve("..");
const docs = join(repo, "docs");
const dist = resolve("dist");
const blob = "https://github.com/StuCM/claude-memory-graph/blob/main/";
const tree = "https://github.com/StuCM/claude-memory-graph/tree/main/";

function* pages(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* pages(p);
    else if (name === "index.html") yield p;
  }
}

let fixed = 0;
for (const page of pages(dist)) {
  const route = relative(dist, dirname(page));            // "" or "future/ROADMAP"
  const source = join(docs, route ? `${route}.md` : "index.md");
  if (!existsSync(source)) continue;
  const html = readFileSync(page, "utf8").replace(/href="(\.\.?\/[^"#]*)(#[^"]*)?"/g, (all, href, hash = "") => {
    const target = resolve(dirname(source), href);
    const rel = relative(repo, target).split("\\").join("/");
    if (rel.startsWith("..") || !existsSync(target)) return all;
    fixed++;
    const inDocs = rel.startsWith("docs/") && !rel.startsWith("docs/tasks/") && rel.endsWith(".md");
    if (inDocs) {
      const r = posix.join("/", rel.slice("docs/".length, -".md".length)).replace(/\/index$/, "/");
      return `href="${r}${hash}"`;
    }
    return `href="${statSync(target).isDirectory() ? tree : blob}${rel}${hash}"`;
  });
  writeFileSync(page, html);
}
console.log(`fix-links: rewrote ${fixed} repo-relative link(s)`);
