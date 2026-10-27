# How Osiris works when a player uses it

This page follows real actions from the phone to the database and back, and names the service that
handles each step. Setup and open steps are in `docs/deployment/production.md`.

```
 Phone (Android / iOS app)            Admin's browser
        |                                   |
        |  HTTPS  api.osiris.fit            |  HTTPS  admin.osiris.fit
        v                                   v
 +---------------------------------------------------+
 | Cloudflare edge (nearest city to the player)       |
 | TLS, WAF, rate rules, adds X-Origin-Verify header  |
 +---------------------------------------------------+
        |                                   |
        v                                   v
 Render: osiris-api (FastAPI)        Render: osiris-admin (static files)
   |  checks the header, the login token, the rate limit
   |---- rate-limit counts ----> Upstash Redis
   |---- reads and writes -----> Supabase PostgreSQL (session pooler)
                                        ^
 Render cron: osiris-db-backup ---------+ nightly dump, encrypted ---> Cloudflare R2
```

## The services, in one line each

- **Cloudflare** owns the `osiris.fit` name and stands in front of everything. Phones connect to
  Cloudflare, never directly to the server, so attacks and floods stop there.
- **Render** runs the API: the same Docker image the tests use, restarted automatically if it crashes,
  redeployed on every push to `master`. It also serves the admin console's files.
- **Supabase** runs the PostgreSQL database: every player, run, challenge and crystal is a row there.
- **Upstash** is a small, fast Redis store. The API keeps short-lived counters there, for example "how
  many login attempts from this IP in the last minute".
- **R2** is Cloudflare's file storage. It holds the nightly encrypted copies of the database, so the data
  survives even if the database is lost.

## 1. Opening the app

1. The phone looks up `api.osiris.fit`. Cloudflare's DNS answers with the address of its nearest data
   centre. For a player in Halifax that is Halifax itself (`YHZ`), a few milliseconds away.
2. The phone opens an encrypted TLS connection to that data centre. Cloudflare checks the request
   against its firewall rules, then forwards it to Render in Oregon over a second encrypted connection.
   It adds a secret header, `X-Origin-Verify`, on the way.
3. The API's first check is that header. A request without it did not come through Cloudflare, for
   example someone calling the Render address directly to skip the firewall, and it is refused.
4. The app asks for the Today screen with the login token it keeps in the phone's secure storage
   (Android Keystore, iOS Keychain). The API checks the token's signature and expiry, then that the
   account is not suspended or signed out everywhere.
5. The API reads the player's quest, week and challenges from Supabase and answers in JSON, compressed.
   The answer carries an ETag, a fingerprint of the content. Next time the app sends the fingerprint
   back; if nothing changed the API answers `304 Not Modified` with no body, which saves data and battery.

## 2. Recording a run

1. The phone records GPS points locally while the player runs, even with the screen off and with no
   signal. Nothing depends on being online during the run.
2. Points are uploaded in batches. Each batch is checked: in order, plausible timestamps, not too many
   too fast (rate limited per IP address, with the counts kept in Upstash).
3. At finish, the API's verifier replays the route: speed between points, gaps, GPS accuracy, distance
   and duration. It decides accepted or rejected, records why, and computes moving time and climb with
   the same auto-pause rule the phone used live.
4. An accepted run earns XP, advances the daily quest and weekly goal, and may complete a challenge.
   All of it is written in one database transaction: either everything is saved or nothing is.
5. Crystals (the paid currency) can only move through one function, the ledger, which writes an
   append-only record for every change. A check script proves the records add up to every balance.

## 3. Leaderboards and the rest of the social tab

Boards are expensive to compute (every verified run of every player), so the API keeps each board for
60 seconds and sorts it once. Every request swaps in the viewer's own live total, so a player sees
their new run at once while everyone else's numbers may lag by up to a minute. Players who did not
opt in to leaderboards appear as "Private".

## 4. Privacy along the way

- Raw GPS points are personal data. They are deleted 45 days after a run, and raw sensor data after
  90 days. The run's summary (distance, time, verdict) is kept.
- Camera exercises are counted on the phone; video and body landmarks never leave it. Only the set's
  summary is uploaded, and only with the player's consent.
- A player can export everything held about them, or erase the account. Erasure deletes personal data
  and keeps an anonymous placeholder, so others' challenge results and the money records stay consistent.
- The database is not reachable from the internet with the public Supabase keys: every table has
  row-level security on and the public roles have no access. Only the API, with its own credentials,
  reads and writes it.

## 5. When something goes wrong

- **Too many requests** from one IP (for example password guessing): Cloudflare's rate rule or the API's
  own limit answers `429` before any password is checked.
- **The API crashes**: Render notices the failed health check (`/healthz`) and restarts it. A bad deploy
  can be rolled back in the Render dashboard.
- **Upstash is down**: the API counts rate limits on its own instead and keeps serving players.
- **The database is lost or corrupted**: restore last night's encrypted copy from R2 (steps in the
  production doc). At most a day of changes is lost.

## 6. Growing

One API instance handles the pilot comfortably (it uses 90 MB of 512 MB at idle). To serve more
players:

1. Add instances in Render. Upstash keeps their rate limits shared.
2. Run the background jobs (decay, retention, settlement) exactly once. Render instances of one
   service share their settings, so set `OSIRIS_RUN_SCHEDULER=0` on the web service and run the jobs
   in a separate Render background worker with `OSIRIS_RUN_SCHEDULER=1`.
3. Raise the Supabase plan when connections or storage near their limits. Keep the API's
   connection pool (5 + 5 per instance) under the pooler's limit.
