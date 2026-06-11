/* ───────────────────────────────────────────────────────────
 *  Osiris Admin – Shared API types
 * ─────────────────────────────────────────────────────────── */

export interface AdminLoginResponse {
  role: string;
  id: number;
  email: string;
  name: string;
  access_token: string;
  message: string;
}

export interface Merchant {
  id: number;
  name: string;
  email: string;
  business_type: string;
  is_active: boolean;
  payment_status: string;
  pilot_fee_cents: number;
  last_payment_at: string | null;
  created_at: string;
}

export interface PlatformRevenue {
  total_crystals: number;
  row_count: number;
  by_source: Record<string, number>;
}

export interface Bounty {
  id: number;
  title: string;
  description: string;
  bounty_type: string;
  completions_remaining: number;
  completions_count: number;
  radius_m: number;
  target_lat: number;
  target_lng: number;
  xp_reward: number;
  crystal_reward: number;
  is_active: number;
}

export interface CreateBountyPayload {
  title: string;
  description: string;
  bounty_type: string;
  completions_remaining: number;
  radius_m: number;
  target_lat: number;
  target_lng: number;
  xp_reward: number;
  crystal_reward: number;
}

export interface AdminUser {
  id: number;
  name: string;
  email: string;
  role: string;
}
