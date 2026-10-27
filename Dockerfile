# A memory server in a container: for hosting a handover share (read-only,
# the default here) or your own store somewhere always-on.
#
#   docker build -t memory-graph .
#   docker run -p 8848:8848 -e MEMORY_GRAPH_TOKEN=<secret> \
#       -v /path/to/handover:/data memory-graph
#
# Serving your own store read-write instead: override the command without
# --read-only (and point /data at a copy you are happy to have edited).
# See docs/REMOTE.md before exposing it beyond a private network.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY claude_memory_graph ./claude_memory_graph
RUN uv sync --locked --no-dev

ENV MEMORY_GRAPH_STATE=/state
EXPOSE 8848
VOLUME ["/data"]
CMD ["uv", "run", "--no-dev", "claude-memory-graph", "serve", "--store", "/data", \
     "--read-only", "--host", "0.0.0.0", "--port", "8848"]
