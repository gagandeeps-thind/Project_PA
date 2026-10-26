"""Origin lock: only requests that came through the CDN reach the API.

The CDN (Cloudflare) adds `X-Origin-Verify: <OSIRIS_ORIGIN_SECRET>` to every request it forwards.
With the setting present, any request without that exact header is refused with 403, so the
platform's own hostname (for example `*.onrender.com`) cannot be used to skip the CDN's WAF and
rate limits. `/healthz` stays open because the platform's health check calls the origin directly.
Without the setting the check is off, which is what dev, CI and a deployment with no CDN need.
"""
import hmac
import json
import logging

import settings

HEADER = b"x-origin-verify"
OPEN_PATHS = frozenset({"/healthz"})

logger = logging.getLogger(__name__)


class OriginGuardMiddleware:
    """Pure ASGI middleware, so a refused request never reaches routing or the body parser."""

    def __init__(self, app, secret: str | None = None) -> None:
        self.app = app
        value = secret if secret is not None else settings.secret("OSIRIS_ORIGIN_SECRET")
        self.secret = value.encode() if value else None
        if self.secret is None and not settings.is_dev_env():
            logger.warning("OSIRIS_ORIGIN_SECRET is unset: requests that bypass the CDN are accepted")

    async def __call__(self, scope, receive, send) -> None:
        if self.secret is None or scope["type"] != "http" or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        given = next((v for k, v in scope["headers"] if k == HEADER), b"")
        if hmac.compare_digest(given, self.secret):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"detail": "Forbidden"}).encode()
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
