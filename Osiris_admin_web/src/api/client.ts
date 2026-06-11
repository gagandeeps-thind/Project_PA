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
