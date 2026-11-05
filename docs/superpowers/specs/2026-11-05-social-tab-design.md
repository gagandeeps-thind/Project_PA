# Social tab: Instagram-style home for a fitness app

Date: 2026-11-05. Status: built from the owner's brief (see "Brief").

## Brief (owner's words, condensed)
The 4th tab (Social) becomes a replica of Instagram's home page: posts from people you follow.
Top bar, left to right: **+** (post a photo, one or more past workout stats / charts, or all together),
**Discover** (a "for you" page of suggested posts based on the player's interests), **Search** (find
people by username or name) and **Messages** (DM followers). Improve it for what a fitness app needs.

## Decisions
- The existing global leaderboards, local rankings and communities move into Discover, so nothing the
  old Social tab offered is lost.
- Home keeps its "People's Posts" (public posts from everyone). The Social feed shows only the player's
  own posts and posts by people they follow.
- **Workout attachments are server-sourced.** The composer sends training session ids; the server copies
  the stats from its own `training_sessions` rows (invariant 2: never trust client totals). Up to 4
  sessions per post. The optional chart is "weekly_progress": the player's last 8 weeks of training
  minutes, computed on the server at post time and frozen into the post.
- **Photos** follow the Arise domain-photo pattern: a base64 JPEG of at most 300 KB, stored in the DB
  (`post_photos`). It is served at `/api/v2/social/media/{token}` where the token is 32 random hex
  characters, so a followers-only photo is not enumerable by post id. Move to object storage past ~10k.
- **Direct messages** are allowed between connections (either player follows the other), never across a
  block. Messages are plain text, at most 1000 characters. Conversations are derived from messages by
  `pair_key` ("<low id>:<high id>"); there is no conversation table.
- **Search** matches display name or handle (referral code), case-insensitive, at least 2 characters,
  excludes suspended and blocked players.
- **Discover ranking** ("for you"): public posts from players the viewer does not follow, from the last
  30 days, scored by shared activity keys with the viewer's own training, plus engagement
  (reactions + 2 x comments) and a recency decay. Optional activity filter chip.
- Fitness touches: an "Active today" row (stories-row look) of followed players who trained today;
  post cards show verified stat tiles (distance, time, pace, reps, average heart rate) and a mini bar
  chart; profiles show posts, followers, following, streak and this week's training minutes.
- Followers-only visibility is now enforced on react, comment, comment list and share (it was not).
- Players can delete their own posts.

## API (all under `get_active_player`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v2/social/feed?limit&before_id` | following feed + `active_today` |
| GET | `/api/v2/social/discover?limit&offset&activity` | for-you posts |
| GET | `/api/v2/social/search?q&limit` | people search |
| GET | `/api/v2/social/users/{id}` | profile + recent posts |
| POST | `/api/v2/social/posts` | compose (caption, photo, session ids, chart, visibility) |
| DELETE | `/api/v2/social/posts/{id}` | delete own post |
| GET | `/api/v2/social/media/{token}` | post photo (public, unguessable) |
| GET | `/api/v2/social/conversations` | inbox + `unread_total` |
| GET | `/api/v2/social/conversations/{user_id}/messages?before_id&limit` | thread |
| POST | `/api/v2/social/conversations/{user_id}/messages` | send |
| POST | `/api/v2/social/conversations/{user_id}/read` | mark read |

`FeedPostOut` gains `photo_url`, `attachments` and `chart`, so Home shows them too.

## Schema (one additive migration)
- `post_photos(id, post_id unique FK, token unique, jpeg, created_at)`
- `direct_messages(id, sender_id FK, recipient_id FK, pair_key, body, created_at, read_at)`;
  indexes on `(pair_key, id)` and `(recipient_id, read_at)`.
- `social_posts.attachments_json` (text, default `[]`) and `social_posts.chart_json` (nullable).
- GDPR: both tables join the export and erasure.

## Client
- `shared/domain`: `model/Social.kt`, `repository/SocialRepository.kt`.
- `shared/data`: `network/api/SocialApi.kt`, `repository/SocialRepositoryImpl.kt`, wired in `DataGraph`.
- `shared/presentation/social`: feed, discover, search, inbox, chat, composer and profile view models,
  factories in `AppGraph`, jvmTests with fakes.
- Android `ui/social/`: the tab screen plus pushed routes for composer, discover, search, inbox, chat and
  profile.

## Testing
- Backend: the scenarios extend `tests/test_home_social_feed.py`, which CI already runs.
- Shared: jvmTests for the view models.
- Emulator QA needs the owner's machine; this session's container has no Android SDK.
