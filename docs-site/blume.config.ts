import { defineConfig } from "blume";

// The site is built from ../docs, the same Markdown the repo links to.
// docs/tasks is the working backlog, not documentation.
export default defineConfig({
  title: "claude-memory-graph",
  description: "Persistent, structured long-term memory for Claude Code.",
  content: {
    root: "../docs",
    exclude: ["tasks/**"],
  },
  github: {
    owner: "StuCM",
    repo: "claude-memory-graph",
    dir: "docs",
  },
});
