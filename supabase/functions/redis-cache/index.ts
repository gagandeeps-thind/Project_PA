// Redis cache backed by Upstash (REST). POST a JSON command:
//   { "action": "ping" }
//   { "action": "get", "key": "leaderboard:distance:week" }
//   { "action": "set", "key": "...", "value": <any JSON>, "ttl": 300 }   // secret key only
//   { "action": "del", "key": "..." }                                    // secret key only
//
// Requires UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN: locally from supabase/functions/.env,
// in the cloud from `supabase secrets set --env-file supabase/functions/.env`.
//
// Auth: every call needs an `apikey` header. A publishable key may only ping and read; writes need the
// secret key, because publishable keys ship inside apps and anyone holding one could otherwise overwrite
// or delete cached values. All keys live under a "cache:" prefix so this endpoint can never touch other data.

import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";
import { Redis } from "@upstash/redis";

const KEY_PREFIX = "cache:";
const MAX_KEY_LENGTH = 200;
const DEFAULT_TTL_SECONDS = 300;
const MAX_TTL_SECONDS = 86_400;
const MAX_VALUE_BYTES = 512 * 1024;

const url = Deno.env.get("UPSTASH_REDIS_REST_URL");
const token = Deno.env.get("UPSTASH_REDIS_REST_TOKEN");
const redis = url && token ? new Redis({ url, token }) : null;

type Command = { action?: string; key?: unknown; value?: unknown; ttl?: unknown };

const fail = (status: number, error: string) => Response.json({ error }, { status });

function cacheKey(key: unknown): string | null {
  if (typeof key !== "string" || key.length === 0 || key.length > MAX_KEY_LENGTH) return null;
  return KEY_PREFIX + key;
}

export default {
  fetch: withSupabase({ auth: ["publishable", "secret"] }, async (req, ctx) => {
    if (req.method !== "POST") return fail(405, "Use POST with a JSON body");
    if (!redis) return fail(500, "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are not set");

    let cmd: Command;
    try {
      cmd = await req.json();
    } catch {
      return fail(400, "Body must be JSON");
    }

    const action = cmd.action ?? "ping";
    const canWrite = ctx.authMode === "secret";

    try {
      switch (action) {
        case "ping": {
          const started = performance.now();
          const pong = await redis.ping();
          return Response.json({
            ok: pong === "PONG",
            redis: pong,
            latency_ms: Math.round(performance.now() - started),
            region: Deno.env.get("SB_REGION") ?? Deno.env.get("DENO_REGION") ?? "local",
          });
        }
        case "get": {
          const key = cacheKey(cmd.key);
          if (!key) return fail(400, `key must be a string of 1-${MAX_KEY_LENGTH} characters`);
          const [value, ttl] = await Promise.all([redis.get(key), redis.ttl(key)]);
          return Response.json({ key: cmd.key, hit: value !== null, value, ttl: value === null ? null : ttl });
        }
        case "set": {
          if (!canWrite) return fail(403, "Writing to the cache needs the secret key");
          const key = cacheKey(cmd.key);
          if (!key) return fail(400, `key must be a string of 1-${MAX_KEY_LENGTH} characters`);
          if (cmd.value === undefined) return fail(400, "value is required");
          if (new TextEncoder().encode(JSON.stringify(cmd.value)).length > MAX_VALUE_BYTES) {
            return fail(413, `value is larger than ${MAX_VALUE_BYTES} bytes`);
          }
          const ttl = cmd.ttl === undefined ? DEFAULT_TTL_SECONDS : Number(cmd.ttl);
          if (!Number.isInteger(ttl) || ttl < 1 || ttl > MAX_TTL_SECONDS) {
            return fail(400, `ttl must be a whole number of seconds from 1 to ${MAX_TTL_SECONDS}`);
          }
          await redis.set(key, cmd.value, { ex: ttl });
          return Response.json({ key: cmd.key, stored: true, ttl });
        }
        case "del": {
          if (!canWrite) return fail(403, "Deleting from the cache needs the secret key");
          const key = cacheKey(cmd.key);
          if (!key) return fail(400, `key must be a string of 1-${MAX_KEY_LENGTH} characters`);
          return Response.json({ key: cmd.key, deleted: (await redis.del(key)) > 0 });
        }
        default:
          return fail(400, "action must be ping, get, set or del");
      }
    } catch (error) {
      console.error("redis-cache", action, error);
      return fail(502, "Redis request failed");
    }
  }),
};

/* Invoke (deployed):

  curl -i -X POST 'https://<project-ref>.supabase.co/functions/v1/redis-cache' \
    -H 'apikey: <publishable or secret key>' -H 'Content-Type: application/json' \
    -d '{"action":"ping"}'
*/
