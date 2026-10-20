"""Conditional GET for JSON API responses.

Every successful JSON GET gets a weak ETag computed from its body. A client that sends the
same value back in If-None-Match receives a bodyless 304, so polling screens (today, hub,
leaderboards) cost a round trip instead of a payload. Responses also get a Cache-Control:
`private, no-cache` by default (store it, but revalidate before reuse; never in a shared
cache, because nearly every route is per-player), or a short public max-age for the few
routes that read no player data.

Pure ASGI rather than BaseHTTPMiddleware so websockets and non-GET requests pass straight
through without being wrapped.
"""
import hashlib

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Routes that read no player data and change only on deploy.
PUBLIC_MAX_AGE = {"/api/v2/rules": 300}


def _etag(body: bytes) -> str:
    return 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'


def _matches(if_none_match: str, etag: str) -> bool:
    if if_none_match.strip() == "*":
        return True
    # Compare weakly: an intermediary may have turned a strong tag into a weak one.
    wanted = etag.removeprefix("W/")
    return any(tag.strip().removeprefix("W/") == wanted for tag in if_none_match.split(","))


class ConditionalGetMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        if_none_match = Headers(scope=scope).get("if-none-match")
        path = scope["path"]
        start: Message | None = None
        chunks: list[bytes] = []
        passthrough = False

        async def capture(message: Message) -> None:
            nonlocal start, passthrough
            if message["type"] == "http.response.start":
                headers = Headers(raw=message["headers"])
                cacheable = message["status"] == 200 and headers.get("content-type", "").startswith(
                    "application/json") and "etag" not in headers
                if not cacheable:
                    passthrough = True
                    await send(message)
                    return
                start = message
                return
            if passthrough or start is None:
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return
            body = b"".join(chunks)
            tag = _etag(body)
            headers = MutableHeaders(raw=start["headers"])
            headers["ETag"] = tag
            if "cache-control" not in headers:
                max_age = PUBLIC_MAX_AGE.get(path)
                headers["Cache-Control"] = f"public, max-age={max_age}" if max_age else "private, no-cache"
            if if_none_match and _matches(if_none_match, tag):
                del headers["content-length"]
                if "content-type" in headers:
                    del headers["content-type"]
                await send({"type": "http.response.start", "status": 304, "headers": headers.raw})
                await send({"type": "http.response.body", "body": b""})
                return
            await send(start)
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)
