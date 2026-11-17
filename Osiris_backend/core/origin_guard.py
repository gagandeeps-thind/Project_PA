"""Origin lock: only requests that came through the CDN reach the API.

The CDN (Cloudflare) adds `X-Origin-Verify: <OSIRIS_ORIGIN_SECRET>` to every request it forwards.
With the setting present, any request without that exact header is refused with 403, so the
platform's own hostname (for example `*.onrender.com`) cannot be used to skip the CDN's WAF and
rate limits. `/healthz` stays open because the platform's health check calls the origin directly.
Without the setting the check is off, which is what dev, CI and a deployment with no CDN need, except that
`OSIRIS_ENV=production` refuses to boot without it (every player would share one rate-limit bucket and
the CDN could be skipped) unless `OSIRIS_ALLOW_NO_CDN=1` says the deployment has no CDN on purpose.
WebSocket upgrades are checked too; a refused one is closed before accept, which the client sees as 403.
"""
import hmac
import json
import logging
import os

import settings

HEADER = b"x-origin-verify"
OPEN_PATHS = frozenset({"/healthz"})

logger = logging.getLogger(__name__)


def assert_boot_config() -> None:
    """Called at import of main, so a production deploy without the origin lock fails its boot."""
    no_cdn_ok = os.environ.get("OSIRIS_ALLOW_NO_CDN") == "1"
    if settings.environment() == "production" and not settings.secret("OSIRIS_ORIGIN_SECRET") and not no_cdn_ok:
        raise RuntimeError(
            "OSIRIS_ORIGIN_SECRET is required when OSIRIS_ENV=production: set it to the value the CDN sends "
            "as X-Origin-Verify, or set OSIRIS_ALLOW_NO_CDN=1 for a deployment that has no CDN."
        )


class OriginGuardMiddleware:
    """Pure ASGI middleware, so a refused request never reaches routing or the body parser."""

    def __init__(self, app, secret: str | None = None) -> None:
        self.app = app
        value = secret if secret is not None else settings.secret("OSIRIS_ORIGIN_SECRET")
        self.secret = value.encode() if value else None
        if self.secret is None and not settings.is_dev_env():
            logger.warning("OSIRIS_ORIGIN_SECRET is unset: requests that bypass the CDN are accepted")

    async def __call__(self, scope, receive, send) -> None:
        if self.secret is None or scope["type"] not in ("http", "websocket") or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        given = next((v for k, v in scope["headers"] if k == HEADER), b"")
        if hmac.compare_digest(given, self.secret):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"detail": "Forbidden"}).encode()
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
