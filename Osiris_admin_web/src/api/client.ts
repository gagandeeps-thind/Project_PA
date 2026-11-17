/* ───────────────────────────────────────────────────────────
 *  Osiris Admin – Axios API client
 * ─────────────────────────────────────────────────────────── */
import axios from "axios";
import type {
  AdminLoginResponse,
  Merchant,
  PlatformRevenue,
  Bounty,
  CreateBountyPayload,
  ReviewQueueItem,
  AdminChallenge,
  AdminUserStatus,
  AuditEvent,
  Funnel,
  AdminCommunity,
  AdminReport,
  SeasonOut,
  AdminExerciseSet,
  AdminExerciseReviewResult,
  TrainingActivity,
  GroupChallenge,
  CreateOfficialChallengePayload,
} from "./types";

const CONFIGURED_URL: string | undefined = import.meta.env.VITE_API_BASE_URL;

/** Non-empty when a production build was made without VITE_API_BASE_URL. main.tsx shows it
 *  instead of the console, so a misbuilt deploy never calls localhost from an admin's browser. */
export const API_CONFIG_ERROR =
  CONFIGURED_URL || import.meta.env.DEV
    ? ""
    : "This console was built without VITE_API_BASE_URL, so it does not know where the Osiris API is. " +
      "Set it in the build environment and deploy again.";

// Only `vite dev` reaches the fallback: a production build without the variable is blocked above.
const BASE_URL = CONFIGURED_URL || "http://localhost:8000";

/** Rows per page on every server-paged list. */
export const PAGE_SIZE = 50;
/** The server returns at most this many official challenges and has no offset for them. */
export const OFFICIAL_CHALLENGE_CAP = 200;

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

/* ── Auth interceptor ────────────────────────────────────── */
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("admin_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/* ── Expired or revoked session ──────────────────────────── */
const LOGIN_PATH = "/api/v1/auth/login";
let unauthorizedHandler: (() => void) | null = null;

/** Called once when an authenticated request answers 401 (the token expired or was revoked),
 *  so the app can return to the login screen instead of showing errors on every page.
 *  Returns a function that removes the handler. */
export function onUnauthorized(handler: () => void): () => void {
  unauthorizedHandler = handler;
  return () => {
    if (unauthorizedHandler === handler) unauthorizedHandler = null;
  };
}

/* ── Short-lived GET cache ───────────────────────────────── */
/* Returning to a page within the TTL reuses the last answer instead of refetching. Any write
 * (sign-in included, and failed writes too, since a timed-out write may still have landed)
 * empties it, so a list reloaded after an action is always fresh. */
const CACHE_TTL_MS = 15_000;
const CACHE_MAX_ENTRIES = 100;
const cache = new Map<string, { at: number; data: unknown }>();
let cacheEpoch = 0;

function clearCache() {
  cache.clear();
  cacheEpoch += 1;
}

type Params = Record<string, string | number | undefined>;

async function get<T>(url: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  const key = `${url}?${JSON.stringify(params)}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return hit.data as T;
  const epoch = cacheEpoch;
  const { data } = await api.get<T>(url, { params, signal });
  // An answer that was in flight while a write landed may predate it: do not keep it.
  if (epoch === cacheEpoch) {
    if (cache.size >= CACHE_MAX_ENTRIES) cache.clear();
    cache.set(key, { at: Date.now(), data });
  }
  return data;
}

api.interceptors.response.use(
  (response) => {
    if (response.config.method !== "get") clearCache();
    return response;
  },
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      if (error.config?.method !== "get") clearCache();
      if (error.response?.status === 401 && error.config?.url !== LOGIN_PATH) {
        clearCache();
        unauthorizedHandler?.();
      }
    }
    return Promise.reject(error);
  }
);

/* ── Auth ─────────────────────────────────────────────────── */
export async function loginAdmin(
  email: string,
  password: string
): Promise<AdminLoginResponse> {
  const { data } = await api.post<AdminLoginResponse>(LOGIN_PATH, {
    email,
    password,
    device_timestamp: new Date().toISOString(),
  });

  // MUST reject non-admin roles
  if (data.role !== "admin") {
    throw new Error("ACCESS DENIED – admin credentials required.");
  }

  return data;
}

/* ── Merchants ────────────────────────────────────────────── */
/** The server has no paging for merchants: this is the whole list for the filter. */
export function getMerchants(status?: string, signal?: AbortSignal): Promise<Merchant[]> {
  return get<Merchant[]>("/api/v1/admin/merchants", { status }, signal);
}

export async function activateMerchant(id: number): Promise<void> {
  await api.post(`/api/v1/admin/merchants/${id}/activate`);
}

export async function deactivateMerchant(id: number): Promise<void> {
  await api.post(`/api/v1/admin/merchants/${id}/deactivate`);
}

/* ── Revenue ──────────────────────────────────────────────── */
export function getPlatformRevenue(signal?: AbortSignal): Promise<PlatformRevenue> {
  return get<PlatformRevenue>("/api/v1/platform/revenue", {}, signal);
}

/* ── Bounties ─────────────────────────────────────────────── */
/** The server has no paging for bounties: this is every bounty in the radius. */
export function getNearbyBounties(
  lat: number,
  lng: number,
  radiusKm: number,
  signal?: AbortSignal
): Promise<Bounty[]> {
  return get<Bounty[]>("/api/v1/bounties/nearby", { lat, lng, radius_km: radiusKm }, signal);
}

export async function createBounty(
  payload: CreateBountyPayload
): Promise<Bounty> {
  const { data } = await api.post<Bounty>("/api/v1/bounties", payload);
  return data;
}

/* ── Errors ───────────────────────────────────────────────── */

/** The message to show for a failed request: the server's `detail` (a string, a v2
 *  `{code, message}`, or a list of validation errors), or a network hint. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    // FastAPI validation errors (422): a list of {loc, msg}.
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d: { loc?: unknown[]; msg?: unknown }) => {
          const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : undefined;
          return field ? `${String(field)}: ${String(d.msg)}` : String(d.msg);
        })
        .join("; ");
    }
    if (!err.response) return "Cannot reach the Osiris API. Check your connection.";
  }
  return err instanceof Error ? err.message : fallback;
}

/* ── Trust console (R2, /api/v2/admin) ───────────────────── */
export function getReviewQueue(offset = 0, signal?: AbortSignal): Promise<ReviewQueueItem[]> {
  return get<ReviewQueueItem[]>("/api/v2/admin/review-queue", { limit: PAGE_SIZE, offset }, signal);
}

export async function reviewAttempt(
  attemptId: number,
  decision: "accept" | "reject",
  note: string
): Promise<void> {
  await api.post(`/api/v2/admin/attempts/${attemptId}/review`, { decision, note });
}

export function getAdminChallenges(status?: string, offset = 0, signal?: AbortSignal): Promise<AdminChallenge[]> {
  return get<AdminChallenge[]>("/api/v2/admin/challenges", { status, limit: PAGE_SIZE, offset }, signal);
}

export async function setChallengeStatus(
  challengeId: number,
  action: "suspend" | "resume" | "void",
  reason: string
): Promise<AdminChallenge> {
  const { data } = await api.post<AdminChallenge>(
    `/api/v2/admin/challenges/${challengeId}/status`,
    { action, reason }
  );
  return data;
}

export async function suspendCourse(courseId: number, reason: string): Promise<void> {
  await api.post(`/api/v2/admin/courses/${courseId}/suspend`, { reason });
}

export async function suspendUser(userId: number, reason: string): Promise<AdminUserStatus> {
  const { data } = await api.post<AdminUserStatus>(`/api/v2/admin/users/${userId}/suspend`, { reason });
  return data;
}

export async function unsuspendUser(userId: number): Promise<AdminUserStatus> {
  const { data } = await api.post<AdminUserStatus>(`/api/v2/admin/users/${userId}/unsuspend`);
  return data;
}

/** Newest first. For the next page pass the last id shown as `before_id`. */
export function getAuditEvents(
  filters: { entity_type?: string; entity_id?: number; action?: string; before_id?: number },
  signal?: AbortSignal
): Promise<AuditEvent[]> {
  return get<AuditEvent[]>("/api/v2/admin/audit-events", { ...filters, limit: PAGE_SIZE }, signal);
}

/* ── Growth release: funnel, communities, seasons, reports ─── */
export function getFunnel(days: number, signal?: AbortSignal): Promise<Funnel> {
  return get<Funnel>("/api/v2/admin/funnel", { days }, signal);
}

export function getAdminCommunities(offset = 0, signal?: AbortSignal): Promise<AdminCommunity[]> {
  return get<AdminCommunity[]>("/api/v2/admin/communities", { limit: PAGE_SIZE, offset }, signal);
}

export async function setCommunityStatus(
  communityId: number,
  change: { verified?: boolean; status?: "active" | "suspended" },
  reason: string
): Promise<AdminCommunity> {
  const { data } = await api.post<AdminCommunity>(`/api/v2/admin/communities/${communityId}/status`, {
    ...change,
    reason,
  });
  return data;
}

export async function createSeason(season: {
  name: string;
  city: string;
  description?: string;
  starts_at: string;
  ends_at: string;
}): Promise<SeasonOut> {
  const { data } = await api.post<SeasonOut>("/api/v2/admin/seasons", season);
  return data;
}

export function getReports(status: string, offset = 0, signal?: AbortSignal): Promise<AdminReport[]> {
  return get<AdminReport[]>("/api/v2/admin/reports", { status, limit: PAGE_SIZE, offset }, signal);
}

export async function resolveReport(
  reportId: number,
  status: "actioned" | "dismissed",
  note: string
): Promise<{ resolved: number }> {
  const { data } = await api.post<{ resolved: number }>(`/api/v2/admin/reports/${reportId}/resolve`, {
    status,
    note,
    all_for_target: true,
  });
  return data;
}

export async function resetDisplayName(userId: number, reason: string): Promise<void> {
  await api.post(`/api/v2/admin/users/${userId}/reset-display-name`, { reason });
}

/* ── Camera-verified exercise review ─────────────────────── */
export function getExerciseSets(
  status: string,
  userId?: number,
  offset = 0,
  signal?: AbortSignal
): Promise<AdminExerciseSet[]> {
  return get<AdminExerciseSet[]>(
    "/api/v2/admin/exercise-sessions",
    { status, user_id: userId || undefined, limit: PAGE_SIZE, offset },
    signal
  );
}

export async function reviewExerciseSet(
  id: number,
  decision: "approve" | "reject",
  note: string
): Promise<AdminExerciseReviewResult> {
  const { data } = await api.post<AdminExerciseReviewResult>(`/api/v2/admin/exercise-sessions/${id}/review`, {
    decision,
    note,
  });
  return data;
}

/* ── Official group challenges (Start tab) ───────────────── */
export function getTrainingActivities(signal?: AbortSignal): Promise<TrainingActivity[]> {
  return get<TrainingActivity[]>("/api/v2/training/activities", {}, signal);
}

export function getOfficialChallenges(signal?: AbortSignal): Promise<GroupChallenge[]> {
  return get<GroupChallenge[]>("/api/v2/admin/group-challenges", {}, signal);
}

export async function createOfficialChallenge(body: CreateOfficialChallengePayload): Promise<GroupChallenge> {
  const { data } = await api.post<GroupChallenge>("/api/v2/admin/group-challenges", body);
  return data;
}
