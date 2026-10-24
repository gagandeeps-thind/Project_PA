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
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

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

api.interceptors.response.use(undefined, (error: unknown) => {
  if (
    axios.isAxiosError(error) &&
    error.response?.status === 401 &&
    error.config?.url !== LOGIN_PATH
  ) {
    unauthorizedHandler?.();
  }
  return Promise.reject(error);
});

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
export async function getMerchants(status?: string): Promise<Merchant[]> {
  const params: Record<string, string> = {};
  if (status) params.status = status;
  const { data } = await api.get<Merchant[]>("/api/v1/admin/merchants", {
    params,
  });
  return data;
}

export async function activateMerchant(id: number): Promise<void> {
  await api.post(`/api/v1/admin/merchants/${id}/activate`);
}

export async function deactivateMerchant(id: number): Promise<void> {
  await api.post(`/api/v1/admin/merchants/${id}/deactivate`);
}

/* ── Revenue ──────────────────────────────────────────────── */
export async function getPlatformRevenue(): Promise<PlatformRevenue> {
  const { data } = await api.get<PlatformRevenue>("/api/v1/platform/revenue");
  return data;
}

/* ── Bounties ─────────────────────────────────────────────── */
export async function getNearbyBounties(
  lat: number,
  lng: number,
  radiusKm: number
): Promise<Bounty[]> {
  const { data } = await api.get<Bounty[]>("/api/v1/bounties/nearby", {
    params: { lat, lng, radius_km: radiusKm },
  });
  return data;
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
export async function getReviewQueue(): Promise<ReviewQueueItem[]> {
  const { data } = await api.get<ReviewQueueItem[]>("/api/v2/admin/review-queue");
  return data;
}

export async function reviewAttempt(
  attemptId: number,
  decision: "accept" | "reject",
  note: string
): Promise<void> {
  await api.post(`/api/v2/admin/attempts/${attemptId}/review`, { decision, note });
}

export async function getAdminChallenges(status?: string): Promise<AdminChallenge[]> {
  const { data } = await api.get<AdminChallenge[]>("/api/v2/admin/challenges", {
    params: status ? { status } : {},
  });
  return data;
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

export async function getAuditEvents(filters: {
  entity_type?: string;
  entity_id?: number;
  action?: string;
}): Promise<AuditEvent[]> {
  const params: Record<string, string | number> = { limit: 200 };
  if (filters.entity_type) params.entity_type = filters.entity_type;
  if (filters.entity_id !== undefined) params.entity_id = filters.entity_id;
  if (filters.action) params.action = filters.action;
  const { data } = await api.get<AuditEvent[]>("/api/v2/admin/audit-events", { params });
  return data;
}

/* ── Growth release: funnel, communities, seasons, reports ─── */
export async function getFunnel(days: number): Promise<Funnel> {
  const { data } = await api.get<Funnel>("/api/v2/admin/funnel", { params: { days } });
  return data;
}

export async function getAdminCommunities(): Promise<AdminCommunity[]> {
  const { data } = await api.get<AdminCommunity[]>("/api/v2/admin/communities");
  return data;
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

export async function getReports(status: string): Promise<AdminReport[]> {
  const { data } = await api.get<AdminReport[]>("/api/v2/admin/reports", { params: { status } });
  return data;
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
export async function getExerciseSets(status: string, userId?: number): Promise<AdminExerciseSet[]> {
  const params: Record<string, string | number> = { status };
  if (userId) params.user_id = userId;
  const { data } = await api.get<AdminExerciseSet[]>("/api/v2/admin/exercise-sessions", { params });
  return data;
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
