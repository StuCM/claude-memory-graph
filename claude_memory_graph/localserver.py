"""This machine's own memory server: one graph for every chat.

With no hosted server set, the plugin's MCP connection, the gate's lookups
and distill all go to `claude-memory-graph serve` on 127.0.0.1:8848. One
process holds the graph, instead of a server per chat each loading it and
racing the others to save it. Nothing needs installing: the session-start
hook calls ensure_running(), which starts the server in the background
when nothing answers, and it keeps running for later chats. A systemd user
service (deploy/systemd/) can own it instead; then this only checks it.

A server this module started from an older plugin version is replaced, so
an update takes effect at the next session; one it didn't start (systemd,
by hand) is left alone. Fail open: if it can't start, the gate reads the
graph from disk and the MCP tools say the server is unreachable.

Only the standard library: this runs on the session-start hook path.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8848"
START_TIMEOUT = 10.0     # seconds to wait for a started server to answer
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def is_local(url: str) -> bool:
    """True when the server is this machine's own (a loopback address)."""
    host = urllib.parse.urlsplit(url if "//" in url else f"//{url}").hostname or ""
    return host in _LOOPBACK


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("claude-memory-graph")
    except Exception:  # noqa: BLE001
        return "?"


def _pidfile() -> Path:
    from .hookcore.state import state_home
    return state_home() / "server.json"


def _get(url: str, timeout: float) -> dict | None:
    """The JSON a server route answers, {} for plain text, None if nothing answers."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
    except (OSError, ValueError):
        return None
    try:
        return json.loads(body)
    except ValueError:
        return {}


def running_version(url: str, timeout: float = 1.0) -> str | None:
    """The version of the server at `url`; "" if it answers but doesn't say
    (an older server); None if nothing answers."""
    base = url.rstrip("/").removesuffix("/mcp")
    if _get(base + "/healthz", timeout) is None:
        return None
    ping = _get(base + "/api/ping", timeout)
    return (ping or {}).get("version", "")


def _ours() -> dict:
    try:
        return json.loads(_pidfile().read_text())
    except (OSError, ValueError):
        return {}


def _stop(pid: int) -> None:
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)       # the server saves the graph as it exits
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)


def _start(url: str) -> int:
    parts = urllib.parse.urlsplit(url)
    host, port = parts.hostname or "127.0.0.1", parts.port or 8848
    from .hookcore.state import state_home
    log = state_home() / "server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        proc = subprocess.Popen(
            [sys.executable, "-m", "claude_memory_graph", "serve",
             "--host", host, "--port", str(port), "--token", ""],
            stdin=subprocess.DEVNULL, stdout=out, stderr=out,
            start_new_session=True,             # outlives this hook and this chat
            env={**os.environ, "MEMORY_GRAPH_TOKEN": ""})
    _pidfile().write_text(json.dumps({"pid": proc.pid, "version": _version(), "url": url}))
    return proc.pid


def ensure_running(url: str = DEFAULT_URL, timeout: float = START_TIMEOUT) -> str:
    """Make sure this machine's server answers at `url`; what happened, in a
    few words ("running", "started", "restarted for v…", or why not). Never
    raises. A remote URL is left alone."""
    if not is_local(url):
        return "remote"
    try:
        return _ensure(url, timeout)
    except Exception as exc:  # noqa: BLE001 - a session must start regardless
        return f"not started: {type(exc).__name__}: {exc}"


def _ensure(url: str, timeout: float) -> str:
    import fcntl
    lock_path = _pidfile().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)    # two chats starting at once start one server
        have = running_version(url)
        ours = _ours()
        mine = ours.get("url") == url and bool(ours.get("pid"))
        if have is not None and (have == _version() or not mine):
            return "running"                # current, or someone else's to manage
        what = "started"
        if have is not None:                # ours, from an older plugin version
            _stop(int(ours["pid"]))
            what = f"restarted for v{_version()}"
        _start(url)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if running_version(url, timeout=0.5) is not None:
                return what
            time.sleep(0.1)
        return f"not answering after {timeout:.0f}s (see {_pidfile().with_name('server.log')})"
