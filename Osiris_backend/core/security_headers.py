"""Browser hardening headers on every API response.

The API serves JSON, photos and a few public HTML pages (legal pages, share and invite cards). None of
them is meant to be framed or sniffed. The CSP allows only what those pages use: inline styles and
same-origin or data: images. A JSON-LD block is data, not script, so it needs no script-src.
HSTS is sent outside dev, where the API is only reached over HTTPS.
"""
import settings

CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
# FastAPI's Swagger UI and ReDoc load scripts from a CDN; they exist only in dev (see main.py).
_DOC_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: adds the headers to the response start, never touches the body."""

    def __init__(self, app) -> None:
        self.app = app
        self.headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
        ]
        if not settings.is_dev_env():
            self.headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with_csp = not scope["path"].startswith(_DOC_PATHS)

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in self.headers if k not in present]
                if with_csp and b"content-security-policy" not in present:
                    extra.append((b"content-security-policy", CSP.encode()))
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)
