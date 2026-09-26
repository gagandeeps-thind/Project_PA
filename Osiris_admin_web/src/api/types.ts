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

/* ── R2 trust console ─────────────────────────────────────── */

export interface ReviewQueueItem {
  attempt_id: number;
  challenge_id: number;
  challenge_title: string;
  user_id: number;
  run_id: number | null;
  elapsed_seconds: number | null;
  target_seconds: number;
  course_coverage: number | null;
  submitted_at: string | null;
}

export interface AdminChallenge {
  id: number;
  title: string;
  status: string;
  status_reason: string | null;
  creator_id: number;
  course_id: number;
  attempt_count: number;
  closes_at: string;
  created_at: string;
}

export interface AdminUserStatus {
  user_id: number;
  email: string;
  suspended: boolean;
  suspension_reason: string | null;
}

export interface AuditEvent {
  id: number;
  actor_type: string;
  actor_id: number | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  details: Record<string, unknown>;
  created_at: string;
}
