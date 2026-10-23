"""Client for the shared server's JSON routes (`claude-memory-graph serve`)."""

import json
import os
import urllib.request


def server_url() -> str:
    return os.environ.get("MEMORY_GRAPH_URL", "http://127.0.0.1:8848").rstrip("/")


def post(path: str, payload: dict, timeout: float = 5.0):
    """The route's JSON answer, or None when no server answers: callers
    fall back to opening the store themselves."""
    req = urllib.request.Request(
        server_url() + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    token = os.environ.get("MEMORY_GRAPH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except (OSError, ValueError):
        return None
