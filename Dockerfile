# The memory server in a container: your own memory, hosted somewhere
# always-on (deploy/ has the compose file that puts HTTPS in front), or a
# read-only handover share.
#
#   docker build -t memory-graph .
#   docker run -p 8848:8848 -e MEMORY_GRAPH_TOKEN=<secret> -v $PWD/data:/data memory-graph
#
# Everything is configured through the environment (see deploy/.env.example):
#   MEMORY_GRAPH_TOKEN       required; what Claude Code machines send
#   MEMORY_GRAPH_PUBLIC_URL  https address; turns on sign-in for the Claude apps
#   MEMORY_GRAPH_PASSWORD    what you type when an app connects (default: token)
#   MEMORY_GRAPH_READ_ONLY=1 serve a handover share: search/recall/query only
# The store is /data/store (graph.nq); sign-ins and logs live in /data/state.
# See docs/REMOTE.md before exposing it beyond a private network.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ceist ./packages/ceist
COPY claude_memory_graph ./claude_memory_graph
RUN uv sync --locked --no-dev

ENV MEMORY_GRAPH_STATE=/data/state \
    MEMORY_GRAPH_PATH=/data/store \
    CLAUDE_CONTEXT_DIR=/data/context
EXPOSE 8848
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8848/healthz', timeout=4)"
CMD ["sh", "-c", "exec uv run --no-dev claude-memory-graph serve --store /data/store \
     --host 0.0.0.0 --port 8848 ${MEMORY_GRAPH_READ_ONLY:+--read-only}"]
