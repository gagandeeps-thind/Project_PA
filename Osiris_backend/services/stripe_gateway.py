"""Stripe payment gateway adapter (Phase 3 — real-money money path).

The SINGLE place the app talks to the Stripe SDK. Nothing else imports `stripe`
directly, so all key handling, fail-closed config, and SDK-shape knowledge lives here.

Responsibilities:
  - load + validate Stripe config (mirrors main.py's JWT / webhook fail-closed pattern)
  - create PaymentIntents (merchant pilot fee + player crystal top-up)
  - verify inbound webhook signatures (stripe.Webhook.construct_event)

Config (env vars — never hard-coded, never committed):
  STRIPE_SECRET_KEY        sk_test_... / sk_live_...   server-side API calls
  STRIPE_WEBHOOK_SECRET    whsec_...                   webhook signature verification
  STRIPE_PUBLISHABLE_KEY   pk_test_... / pk_live_...   handed to the Flutter client (public)

Fail-closed (audit §2.1 parity): in a non-dev OSIRIS_ENV, a missing STRIPE_SECRET_KEY or
STRIPE_WEBHOOK_SECRET makes the app refuse to boot rather than silently disable real
payments or accept forgeable webhooks. In an explicit dev/test OSIRIS_ENV the gateway is
simply DISABLED (`STRIPE_ENABLED is False`) and the payment endpoints return 503 — local
dev and the test suite run without real keys (tests patch these functions).
"""
from __future__ import annotations

import os

import stripe

# An explicit dev/test environment disables Stripe instead of failing the boot, mirroring
# the OSIRIS_WEBHOOK_SECRET handling in main.py. Anything else (including a forgotten/unknown
# OSIRIS_ENV) is treated as production and must be fully configured.
_DEV_ENVS = {"dev", "development", "test", "testing", "local"}
_IS_DEV_ENV = os.environ.get("OSIRIS_ENV", "").lower() in _DEV_ENVS

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")

# Stripe is "on" only when both server-side secrets are present. The publishable key is
# client-facing and not required for the gateway to function.
STRIPE_ENABLED = bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def assert_boot_config() -> None:
    """Fail-closed boot check (audit §2.1 parity). Call this from app startup, NOT at import —
    keeping import side-effect-free means this module never preempts main.py's own JWT/webhook
    boot checks (their error messages must surface first). In a non-dev OSIRIS_ENV a missing
    STRIPE_SECRET_KEY or STRIPE_WEBHOOK_SECRET raises, so a deploy that forgot the keys refuses
    to boot rather than silently disabling real payments / accepting forgeable webhooks."""
    if not STRIPE_ENABLED and not _IS_DEV_ENV:
        missing = [
            name
            for name, value in (
                ("STRIPE_SECRET_KEY", STRIPE_SECRET_KEY),
                ("STRIPE_WEBHOOK_SECRET", STRIPE_WEBHOOK_SECRET),
            )
            if not value
        ]
        raise RuntimeError(
            f"Stripe is not fully configured (missing {missing}). These are REQUIRED unless "
            f"OSIRIS_ENV is one of {sorted(_DEV_ENVS)}. An unset or unknown OSIRIS_ENV is treated "
            "as production: the app refuses to boot rather than silently disable real payments or "
            "accept forgeable webhooks (audit §2.1 parity). For local development set OSIRIS_ENV=dev. "
            "Get the secret key from the Stripe Dashboard (Developers -> API keys) and the webhook "
            "signing secret from the Webhooks page; set both via environment variables / .env."
        )


class StripeNotConfiguredError(RuntimeError):
    """Raised when a payment operation is attempted while Stripe is disabled (dev/test without
    keys). Endpoints translate this into a 503 so the failure is loud, never a silent stub."""


def _require_enabled() -> None:
    if not STRIPE_ENABLED:
        raise StripeNotConfiguredError(
            "Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET."
        )


def create_payment_intent(
    *,
    amount_cents: int,
    currency: str = "usd",
    metadata: dict[str, str],
    description: str | None = None,
    idempotency_key: str | None = None,
) -> "stripe.PaymentIntent":
    """Create a Stripe PaymentIntent and return it (caller reads `.id` and `.client_secret`).

    `metadata` is stamped onto the intent and echoed back on every webhook event for that
    intent — it's how the webhook routes a payment to the right merchant / crystal purchase.
    Stripe requires metadata values to be strings; callers must stringify ids.

    `idempotency_key`, when supplied, lets Stripe collapse accidental duplicate create calls
    (e.g. a double-tapped Pay button) into a single intent.
    """
    _require_enabled()
    return stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency,
        metadata=metadata,
        description=description,
        automatic_payment_methods={"enabled": True},
        idempotency_key=idempotency_key,
    )


def construct_event(payload: bytes, sig_header: str) -> "stripe.Event":
    """Verify a webhook's `Stripe-Signature` header against the raw body and return the parsed
    event. Raises `stripe.error.SignatureVerificationError` on a bad/forged signature and
    `ValueError` on a malformed payload — the endpoint maps both to a 400/401."""
    _require_enabled()
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
