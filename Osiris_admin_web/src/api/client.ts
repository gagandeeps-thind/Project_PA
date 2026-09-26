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
} from "./types";

const BASE_URL = "http://localhost:8000";

const api = axios.create({
  baseURL: BASE_URL,
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

/* ── Auth ─────────────────────────────────────────────────── */
export async function loginAdmin(
  email: string,
  password: string
): Promise<AdminLoginResponse> {
  const { data } = await api.post<AdminLoginResponse>("/api/v1/auth/login", {
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

/* ── Trust console (R2, /api/v2/admin) ───────────────────── */

/** Pull the human message out of a v2 `{detail: {code, message}}` error. */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
  }
  return err instanceof Error ? err.message : fallback;
}

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
