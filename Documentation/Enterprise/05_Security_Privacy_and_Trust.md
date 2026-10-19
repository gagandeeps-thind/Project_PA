# Security, Privacy, and Trust Plan

## 1. Threat model

Primary threats are GPS spoofing and replay, fabricated routes, account takeover, crystal duplication, payment webhook forgery, privacy exposure of routines/home locations, collusion, harassment at challenge locations, unsafe behavior, and insider misuse of admin tools.

## 2. Required controls

### Identity and access

- Argon2id for new password hashes; retain bcrypt migration compatibility only as needed.
- Short-lived access token plus rotating refresh token; device/session list and revoke-all control.
- MFA for admins and support staff.
- Separate roles: player, reviewer, support, finance, admin, service account.
- Least privilege, deny-by-default APIs, and no public exact-domain endpoint.

### Application and supply chain

- Strict CORS allowlist per environment; HTTPS only outside local development.
- Rate limits on auth, route upload, challenge join, payment, and export.
- Dependency lockfiles, Dependabot/Renovate, SAST, secret scanning, container scanning, and signed release artifacts.
- Security headers, input limits, schema validation, SQL parameterization, and safe error messages.
- Payment webhooks verified against raw payload and provider signature; deduplicated by provider event ID.

### Secrets and configuration

- No secret in the repository or in either app. `.env.example` lists every backend setting; `.env` is local only.
- Deployed environments deliver secrets from the secret manager (AWS Secrets Manager via ECS `secrets`,
  Vault Agent, or Kubernetes/Docker secrets) as `NAME` or as a mounted file named by `NAME_FILE`;
  `Osiris_backend/settings.py` reads both. An unreadable `NAME_FILE` fails the boot instead of running unset.
- An unset or unknown `OSIRIS_ENV` counts as production and refuses to boot without its secrets.

### Anti-cheat

- Treat client telemetry as evidence, never truth.
- Bind chunks to run ID, sequence, nonce, device session, and server receipt time.
- Reject impossible speed/acceleration/jumps and suspicious clock skew.
- Use route similarity and start/finish checks; maintain a review queue rather than false certainty.
- Store verifier version and rules/model version on every decision.
- Do not automatically ban from one low-confidence signal; provide appeal and human review.

### Privacy

- PIPEDA/Canadian privacy baseline for the Nova Scotia pilot; extend controls for every later market.
- Separate consent for service verification and optional ML training.
- Precise location is private by default; public views use generalized markers, geohashes, or course abstractions.
- Encrypt in transit and at rest; redact coordinates from logs and support screenshots.
- Retain raw telemetry only as long as needed; preserve aggregated results separately.
- Provide access/export, correction, deletion request, consent history, and retention disclosures.
- Preserve legally required accounting records through irreversible anonymization, not personal identifiers.

## 3. Safety and harm prevention

- Show rest, hydration, weather, lighting, and traffic warnings based on available context.
- Do not generate routes that require crossing unsafe roads or entering private property.
- Allow users to hide from public discovery and report a location/challenge.
- Rate-limit challenges near sensitive places and block exact home-address courses.
- Add age gating and region gating before paid or prize mechanics.

## 4. Security acceptance gates

Before UAT: threat model reviewed, high-risk findings have owners, privacy flows tested, no secret in repository, and map exposure tests pass.  
Before production: external penetration test or equivalent independent review, incident drill complete, restore test complete, admin MFA enforced, and a documented release decision recorded for any paid competition.
