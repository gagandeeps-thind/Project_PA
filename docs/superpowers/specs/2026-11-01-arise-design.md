# Arise: map-first activity tab (design)

Date: 2026-11-01. Status: approved in chat (design, Mapbox, migrations); awaiting spec review.

## Goal

Replace the Discover tab with **Arise**, a full-screen map where players run, walk, hike and trail-run,
record routes that every player can follow, and claim and attack domains. Android only in this round;
iOS only gets the new tab name.

## Decisions

| Topic | Decision |
|---|---|
| Map engine | Mapbox Maps SDK for Android 11.28.0 (`com.mapbox.maps:android-ndk27` + `com.mapbox.extension:maps-compose-ndk27`). The Mapbox Maven repo serves artifacts without a secret token. |
| Token | Public token `MAPBOX_ACCESS_TOKEN` read from `config/environments/local.properties` (gitignored) into a `mapbox_access_token` string resource. Release builds use the same mechanism. |
| Route privacy | The player chooses on save: **Hide start/finish** (default on) trims ~200 m from each end of the public line. |
| Attack rules | Run, then optional workout, as below. No crystals move in Arise attacks; the v1 vault economy is untouched. |
| Heatmaps | From Osiris accepted runs only, ~100 m cells, k ≥ 3 distinct players on shared heatmaps. |
| Migrations | Approved by Gagan on 2026-11-01. |

## 1. Screen

- Tab `Tab.ARISE` (`path = "arise"`); `osiris://discover` still resolves to it.
- Full-screen `MapboxMap`, camera on the player's location (existing location permission flow).
- Right rail, top to bottom: layers button, 2D/3D toggle, locate-me, **+** FAB, attack button (sword icon,
  vector-drawn from the supplied PNG).
- **+** expands upward into *Start route* and *Record route*.
- Pull-up sheet: peek height ≈ 1 cm (≈ 64 dp) above the nav bar, draggable to full height.
  - Normal mode: nearby public routes and the challenge sections Discover shows today.
  - Attack mode: domain carousels **Suggested** and **High difficulty**.
- 3D: camera pitch 60°, terrain from `mapbox.mapbox-terrain-dem-v1` (exaggeration 1.2); 2D: pitch 0, no terrain.
- Layers sheet:
  - Style: Standard (`mapbox://styles/mapbox/standard`), Satellite (`standard-satellite`),
    Hybrid (`satellite-streets-v12`), Winter (`outdoors-v12` + snow effect).
  - Overlays: POIs (Standard `showPointOfInterestLabels`, a symbol layer filter on other styles),
    Bike lanes (line layer on `mapbox-streets-v8` `road` where `class=path, type=cycleway`). Both on by default.
  - Heatmaps: global, weekly, night, personal (one at a time).
  - Terrain: gradient, avalanche gradient, aspect (one at a time).
- Selection is kept in memory for the session.

## 2. Routes

- Both + options open the activity picker: Run, Walk, Hike, Trail.
  - Run, Walk, Hike always enabled.
  - Trail enabled only if Mapbox Tilequery (`mapbox.mapbox-streets-v8`, radius 300 m, layer `landuse`/`landcover`)
    returns `wood`, `forest`, `scrub` or `national_park` near the player. Otherwise greyed out with
    "Trail needs a forest or natural area nearby". If the query fails, Trail stays enabled (fail open, the run is
    still verified server-side).
- *Start route*: a normal tracked run session with the activity type; nothing is published.
- *Record route*: the same session; on finish the player names it and sets **Hide start/finish**.
  On an accepted run the server creates a public course.
- Public routes on the map: a line per route, coloured by activity, with a legend in the sheet. Tapping one
  opens a card with distance, creator benchmark and **Start this route**, which runs a session against that
  course (existing course-attempt verification).

Backend:

- `courses` gains `activity_type` (`run|walk|hike|trail`), `is_public` (bool), `hide_ends` (bool),
  `public_route_json` (the line others see, trimmed when `hide_ends`).
- `run_sessions` gains `activity_type` (default `run`).
- `GET /api/v2/arise/routes?lat&lng&radius_km` → public routes with `public_route_json` only.
- `POST /api/v2/arise/routes` `{run_session_id, name, activity_type, hide_ends}` → creates the public course
  from an accepted run (owner only, one per run).

## 3. Domains and attack

Claim:

1. A recorded run whose finish is within 50 m of its start, and is accepted, may claim the enclosed polygon:
   `POST /api/v2/arise/domains {run_session_id}`. The domain stores `distance_m`, `duration_s`, `area_sqkm`.
2. The app asks **Finish / Exceed**.
   - Finish: done.
   - Exceed: `POST /api/v2/arise/domains/{id}/workout` → the server generates a workout and stores it as pending.
     The player performs it set by set with the camera rep counter (existing pose engine and
     exercise-session submission). `POST .../workout/complete {session_ids}` checks every set was met by an
     accepted exercise session; success sets it as the domain's defense workout, failure discards it.

Workout generator (`services/arise_workouts.py`): deterministic from a seed; total reps 30–100 scaled by player
level (level 1 → 30, +5 per level, cap 100); 3–6 sets from the catalog's `reps` exercises; 10–30 s rest between
sets.

Attack:

- `GET /api/v2/arise/domains?lat&lng&radius_km` → nearby domains with owner name, photo URL, run stats, workout
  summary and a `difficulty` bucket for the caller:
  - **suggested** if the caller's best accepted pace over the last 30 days (s/km) × the domain's distance is below
    the domain's time, and the workout's total reps ≤ the caller's level cap;
  - otherwise **hard**, sorted by how far the caller is from both bars.
- `POST /api/v2/arise/domains/{id}/attack {run_session_id}`: the run must be accepted, enclose the domain's
  centroid, have `distance_m ≥ domain.distance_m` and `duration_s < domain.duration_s`. If the domain has a
  workout, the response asks for it; `POST .../attack/{attack_id}/workout {session_ids}` checks the same sets.
  Win: ownership moves to the attacker, run stats are replaced, the workout is cleared, and the app shows
  Finish/Exceed to the new owner. Loss: the attack is recorded as failed.
- Photo: `PUT /api/v2/arise/domains/{id}/photo` (owner only, JPEG ≤ 300 KB, re-encoded server-side at max
  1024 px), served by `GET /api/v2/arise/domains/{id}/photo` with cache headers.
  Shortcut: stored in the database; move to R2 if domain photos pass ~10k.

Backend tables: `domains` gains `distance_m`, `duration_s`, `defense_workout_json`, `source_run_session_id`;
new `arise_attacks` (attacker, domain, run, status, workout snapshot) and `domain_photos` (domain_id unique,
jpeg bytes, updated_at).

## 4. Heatmaps and terrain

- `GET /api/v2/arise/heatmap?kind=global|weekly|night|personal&bbox=` → `[{lat, lng, w}]` from accepted runs'
  route points, snapped to ~100 m cells, excluding the first and last 200 m of each run. Shared kinds drop cells
  with fewer than 3 distinct players. Night = run start between 20:00 and 05:00 local solar time (UTC + longitude / 15 h, so no
  timezone data is needed).
  Rendered with a Mapbox heatmap layer.
- Terrain layers are computed on the device from `mapbox.terrain-rgb` tiles through a `CustomRasterSource`:
  gradient (0–45°+ ramp), avalanche gradient (27–30 / 30–35 / 35–40 / 40–45 / 45+ ° bands), aspect (8 compass
  colours, only on slopes ≥ 5°). Risk: `CustomRasterSource` is experimental; if it is not usable, the terrain
  layers ship later and this is reported.

## Testing

- Backend: `tests/test_arise.py` covers routes (publish, trim, privacy), domains (claim, loop check), the
  workout generator (bounds, determinism), attack rules (time, distance, enclosure, workout), difficulty buckets,
  photo limits and heatmap k-anonymity.
- Shared Kotlin: `jvmTest` for the Arise view model (modes, sheet content, activity gating, attack flow).
- Emulator: launch, map renders, controls work, record and publish a route against a local API.

## Delivery

Four commits on master, each through the gate and pushed: (1) screen and map, (2) routes, (3) domains and
attack, (4) heatmaps and terrain. agy works in the same tree: new code goes in new files; shared files
(`OsirisRoot.kt`, `AppGraph.kt`, `models.py`, `main.py`, `openapi.json`) are diffed before every edit and only
our hunks are staged.

## Not in this round

iOS Arise screen, offline maps, turn-by-turn navigation to a route start, RTDN-style live domain updates.
