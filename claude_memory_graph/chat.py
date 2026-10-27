"""Chat with the memory, in a browser, on the server that holds it.

The server's home page becomes a chat: you (or a colleague, on a handover
share) sign in with the server password and ask questions; Claude answers
from the graph using the read-only memory tools — search, recall, query,
reflect — run in-process against the server's store. Nobody needs Claude
Code, an MCP client or a token, and the chat can't change the memory.

On when the server has an Anthropic API key (ANTHROPIC_API_KEY). Every
answer is an API call billed to that key, so a daily cap bounds what a
shared link can spend (MEMORY_GRAPH_CHAT_DAILY_LIMIT, default 300 messages).

Conversations live in the server's memory only (lost on restart). Each is
kept whole — assistant turns go back to the API exactly as they came,
thinking blocks included — and capped at MAX_TURNS questions.
"""

import asyncio
import datetime
import json
import logging
import os
import secrets
import time
from types import SimpleNamespace

from . import tools

log = logging.getLogger(__name__)

MODEL = os.environ.get("MEMORY_GRAPH_CHAT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("MEMORY_GRAPH_CHAT_EFFORT", "medium")
MAX_TURNS = 40                 # questions per conversation
MAX_TOOL_ROUNDS = 12           # tool round-trips per answer
MAX_CHATS = 200                # conversations held at once
CHAT_TTL = 24 * 3600           # an idle conversation is dropped after this
SESSION_TTL = 7 * 24 * 3600    # how long a browser stays signed in
MAX_QUESTION = 4000            # characters

SYSTEM = """You are the chat front end of a memory: a knowledge graph of one \
person's working knowledge — projects, decisions and their rationale, patterns \
and gotchas, tasks, people and technologies, linked to each other. {scope}

Answer from the memory, using the tools:
- memory_search finds entry points from free text; start there unless you \
know a node's exact model and name.
- memory_recall (depth 2) on the nodes that matter shows their properties and \
what they link to. Follow links when the question is about how things relate.
- memory_query runs SPARQL, for lists, counts and filters across the graph.
- memory_reflect gives an overview of what the memory holds.

Base every answer on what the tools return. When the memory doesn't hold the \
answer, say so plainly and mention what it does hold nearby; don't fill the \
gap from general knowledge. If general background genuinely helps, keep it \
separate and label it as not from the memory. Name the memories you relied on \
(type and name) so the reader can ask about them. Prefer short answers; use \
lists for several items. The memory is read-only here: if asked to change it, \
explain that this chat can only read."""


def configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _summary(name: str, args: dict) -> str:
    """One line for the UI saying what a tool call looked for."""
    if name == "memory_search":
        return f"searched for “{args.get('text', '')}”"
    if name == "memory_recall":
        return f"recalled {args.get('model', '')} “{args.get('name', '')}”"
    if name == "memory_query":
        return "ran a query over the graph"
    if name == "memory_reflect":
        return "looked over the whole memory"
    return name


class ChatService:
    def __init__(self, store, title: str = "Memory", scope: str = "",
                 client=None, daily_limit: int | None = None):
        self.handlers = tools.handlers(store, read_only=True)
        self.title = title
        self.system = SYSTEM.format(scope=scope).strip()
        self._client = client
        self.daily_limit = daily_limit if daily_limit is not None else int(
            os.environ.get("MEMORY_GRAPH_CHAT_DAILY_LIMIT", "300"))
        self.chats: dict[str, dict] = {}
        self.usage = {"day": "", "count": 0}
        self._tools = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def tool_definitions(self) -> list[dict]:
        if self._tools is None:
            listed = await self.handlers["on_list_tools"](None, None)
            # sorted, so the cached prefix is byte-identical on every request
            self._tools = [{"name": t.name, "description": t.description or "",
                            "input_schema": t.input_schema, "eager_input_streaming": True}
                           for t in sorted(listed.tools, key=lambda t: t.name)]
        return self._tools

    async def run_tool(self, name: str, args) -> tuple[str, bool]:
        if not isinstance(args, dict):
            return "invalid tool input: expected an object", True
        result = await self.handlers["on_call_tool"](
            None, SimpleNamespace(name=name, arguments=args))
        text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
        return text or "(no result)", bool(result.is_error)

    # ------------------------------------------------------------ limits

    def _spend(self) -> bool:
        today = datetime.date.today().isoformat()
        if self.usage["day"] != today:
            self.usage = {"day": today, "count": 0}
        if self.usage["count"] >= self.daily_limit:
            return False
        self.usage["count"] += 1
        return True

    def _chat(self, chat_id: str) -> dict:
        now = time.time()
        for key in [k for k, c in self.chats.items() if now - c["touched"] > CHAT_TTL]:
            del self.chats[key]
        if chat_id not in self.chats and len(self.chats) >= MAX_CHATS:
            oldest = min(self.chats, key=lambda k: self.chats[k]["touched"])
            del self.chats[oldest]
        chat = self.chats.setdefault(chat_id, {"messages": [], "turns": 0, "touched": now})
        chat["touched"] = now
        return chat

    # -------------------------------------------------------------- turn

    async def turn(self, chat_id: str, question: str):
        """Answer one question. Yields UI events: {"type": "text", "text"},
        {"type": "tool", "text"}, {"type": "error", "text"}, {"type": "done"}."""
        question = question.strip()[:MAX_QUESTION]
        if not question:
            yield {"type": "done"}
            return
        chat = self._chat(chat_id)
        if chat["turns"] >= MAX_TURNS:
            yield {"type": "error", "text": "This conversation is long enough; start a new one."}
            return
        if not self._spend():
            yield {"type": "error", "text": "The chat has reached today's message limit."}
            return

        import anthropic
        tool_defs = await self.tool_definitions()
        # work on a copy: a failed turn leaves the conversation as it was
        messages = chat["messages"] + [{"role": "user", "content": question}]
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                async with self.client.beta.messages.stream(
                    model=MODEL, max_tokens=16000,
                    system=self.system, tools=tool_defs, messages=messages,
                    output_config={"effort": EFFORT},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            yield {"type": "text", "text": event.text}
                    response = await stream.get_final_message()

                if response.stop_reason == "refusal":
                    yield {"type": "error", "text": "Claude declined to answer that."}
                    return
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason == "pause_turn":
                    continue
                uses = [b for b in response.content if b.type == "tool_use"]
                if not uses:
                    break
                if response.stop_reason == "max_tokens":
                    yield {"type": "error", "text": "The answer ran too long."}
                    return
                results = []
                for block in uses:
                    yield {"type": "tool", "text": _summary(block.name, block.input
                                                            if isinstance(block.input, dict) else {})}
                    text, is_error = await self.run_tool(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": text, "is_error": is_error})
                messages.append({"role": "user", "content": results})
                if any(b.type == "text" for b in response.content):
                    yield {"type": "text", "text": "\n\n"}   # keep the next part apart
            else:
                yield {"type": "error", "text": "Gave up after too many lookups."}
                return
        except ValueError:
            # a tool input the stream couldn't parse at all
            yield {"type": "error", "text": "Something went wrong reading the memory; ask again."}
            return
        except anthropic.RateLimitError:
            yield {"type": "error", "text": "Claude is busy right now; try again in a minute."}
            return
        except anthropic.AuthenticationError:
            log.error("chat: the server's ANTHROPIC_API_KEY was rejected")
            yield {"type": "error", "text": "The server's Claude API key isn't working."}
            return
        except anthropic.APIStatusError as exc:
            log.warning("chat: API error %s", exc.status_code)
            yield {"type": "error", "text": f"Claude API error ({exc.status_code}); try again."}
            return
        except anthropic.APIConnectionError:
            yield {"type": "error", "text": "Couldn't reach Claude; try again."}
            return
        chat["messages"] = messages
        chat["turns"] += 1
        yield {"type": "done"}


# ------------------------------------------------------------------ web

class Sessions:
    """Browser sign-ins: random cookie values, in memory."""

    def __init__(self):
        self.live: dict[str, float] = {}

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.live = {k: t for k, t in self.live.items() if t > now}
        self.live[token] = now + SESSION_TTL
        return token

    def valid(self, token: str | None) -> bool:
        return bool(token) and self.live.get(token, 0) > time.time()

    def drop(self, token: str | None) -> None:
        self.live.pop(token or "", None)


COOKIE = "mg_chat"


def chat_routes(service: ChatService, auth):
    """/ (the chat, or its sign-in), /chat/login, /chat/logout, /chat/send."""
    from importlib import resources

    from starlette.requests import Request
    from starlette.responses import (HTMLResponse, JSONResponse, RedirectResponse,
                                     StreamingResponse)
    from starlette.routing import Route

    sessions = Sessions()
    page = resources.files("claude_memory_graph").joinpath("chat.html").read_text()
    headers = {"Cache-Control": "no-store", "X-Frame-Options": "DENY",
               "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                          "script-src 'unsafe-inline'; connect-src 'self'; "
                                          "img-src data:; frame-ancestors 'none'"}

    def render(view: str, error: str = "", status: int = 200):
        boot = json.dumps({"view": view, "title": service.title, "error": error,
                           "configured": configured()})
        return HTMLResponse(page.replace("/*BOOT*/null", boot.replace("</", "<\\/")),
                            status_code=status, headers=headers)

    async def home(request: Request):
        signed_in = sessions.valid(request.cookies.get(COOKIE))
        return render("chat" if signed_in else "login")

    async def login(request: Request):
        form = await request.form()
        if auth.locked():
            return render("login", "Too many wrong passwords. Try again in a few minutes.", 429)
        if not auth.check_password(str(form.get("password", ""))):
            await asyncio.sleep(1)
            return render("login", "Wrong password.", 401)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, sessions.create(), max_age=SESSION_TTL, httponly=True,
                            secure=request.url.scheme == "https", samesite="lax")
        return response

    async def logout(request: Request):
        sessions.drop(request.cookies.get(COOKIE))
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(COOKIE)
        return response

    async def send(request: Request):
        if not sessions.valid(request.cookies.get(COOKIE)):
            return JSONResponse({"error": "signed out"}, status_code=401)
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            return JSONResponse({"error": "expected JSON"}, status_code=415)
        if not configured():
            return JSONResponse({"error": "chat is not configured on this server"},
                                status_code=503)
        try:
            body = await request.json()
            chat_id, question = str(body["chat"])[:64], str(body["text"])
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "bad request"}, status_code=400)

        async def events():
            async for event in service.turn(chat_id, question):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store",
                                          "X-Accel-Buffering": "no"})

    return [Route("/", home, methods=["GET"]),
            Route("/chat/login", login, methods=["POST"]),
            Route("/chat/logout", logout, methods=["POST"]),
            Route("/chat/send", send, methods=["POST"])]
