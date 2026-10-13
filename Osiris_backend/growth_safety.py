"""Growth release G4: safety, privacy, and trust.

- Reporting (users, challenges, communities, share cards) with an admin abuse queue.
  Three independent "unsafe route" reports pull a challenge until an admin reviews it.
- Blocking: neither player can join the other's challenges; the blocker stops seeing the
  other's challenges, and their name is hidden on the blocker's leaderboards.
- Consent: an append-only consent ledger; v2 players must grant location consent before
  recording a run.
- Data rights (PRD-009): a full export, and erasure that removes personal data while
  keeping other players' records intact (the account row is anonymised, not deleted, so
  challenges and results others earned stay valid).
- Session security: "sign out everywhere" and password change revoke every older token.
- `GET /api/v2/rules`: plain-language reward, refund, verification, and safety rules.

Imported from the end of growth_api; registers its router on `main.app`.
"""
from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from growth_api import (
    REFERRAL_CAP,
    REFERRAL_MIN_DISTANCE_M,
    REFERRAL_XP,
    delete_growth_data,
    get_or_create_profile,
)
from main import (
    _api_error,
    _audit,
    _now_naive_utc,
    app,
    create_access_token,
    get_active_player,
    get_current_admin,
    get_db,
    get_password_hash,
    get_rank,
    verify_password,
)
from services import leaderboards as lb
from services import player_safety
from services import quests as quest_rules

router = APIRouter()

POLICY_VERSION = "privacy-2026-09"
CONSENT_KINDS = ("location", "public_profile", "leaderboard")
REPORT_TARGETS = ("user", "challenge", "community", "share_card")
REPORT_REASONS = (
    "unsafe_route", "harassment", "cheating", "spam", "inappropriate_name", "privacy", "other",
)
MAX_REPORTS_PER_DAY = 20
UNSAFE_ROUTE_AUTO_SUSPEND = 3
ERASE_CONFIRMATION = "DELETE"
DELETED_NAME = "Deleted runner"


# --- helpers used by main.py and the other growth modules --------------------------

def require_location_consent(db: Session, user_id: int) -> None:
    if player_safety.needs_location_consent(db, user_id):
        raise _api_error(403, "LOCATION_CONSENT_REQUIRED",
                         "Allow Osiris to use your location during runs before you start one")


def record_consent(db: Session, user_id: int, kind: str, granted: bool) -> None:
    db.add(models.ConsentRecord(user_id=user_id, kind=kind, granted=granted, policy_version=POLICY_VERSION))


blocked_user_ids = player_safety.blocked_user_ids
is_blocked_between = player_safety.is_blocked_between


def revoke_sessions(user: models.User) -> None:
    """Refuse every token issued before now. Truncated to the second, which is the
    resolution of the JWT `iat` claim."""
    user.tokens_valid_after = _now_naive_utc().replace(microsecond=0)


# --- schemas ---------------------------------------------------------------------

class ReportCreate(BaseModel):
    target_type: str
    target_id: Optional[int] = None          # challenge id
    target_ref: Optional[str] = Field(default=None, max_length=64)  # user handle, community slug, share token
    reason: str
    details: Optional[str] = Field(default=None, max_length=500)


class ReportOut(BaseModel):
    id: int
    target_type: str
    reason: str
    status: str
    created_at: object
    message: str


class BlockCreate(BaseModel):
    handle: Optional[str] = Field(default=None, max_length=16)
    challenge_id: Optional[int] = None


class BlockOut(BaseModel):
    id: int
    name: str
    created_at: object


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EraseRequest(BaseModel):
    password: str
    confirm: str


class TokenOut(BaseModel):
    access_token: str
    message: str


class AdminReportItem(BaseModel):
    id: int
    target_type: str
    target_id: int
    target_summary: str
    reason: str
    details: Optional[str] = None
    status: str
    open_reports_on_target: int
    created_at: object


class AdminReportResolve(BaseModel):
    status: str
    note: str = Field(min_length=3, max_length=500)
    all_for_target: bool = True


class AdminReason(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# --- reports ---------------------------------------------------------------------

def _resolve_target(db: Session, req: ReportCreate) -> int:
    if req.target_type == "challenge":
        ch = db.query(models.Challenge).filter(models.Challenge.id == (req.target_id or -1)).first()
        if ch is None:
            raise _api_error(404, "TARGET_NOT_FOUND", "Challenge not found")
        return ch.id
    ref = (req.target_ref or "").strip()
    if req.target_type == "user":
        p = db.query(models.PlayerProfile).filter(models.PlayerProfile.referral_code == ref.upper()).first()
        if p is None:
            raise _api_error(404, "TARGET_NOT_FOUND", "Player not found")
        return p.user_id
    if req.target_type == "community":
        c = db.query(models.Community).filter(models.Community.slug == ref).first()
        if c is None:
            raise _api_error(404, "TARGET_NOT_FOUND", "Community not found")
        return c.id
    card = db.query(models.ShareCard).filter(models.ShareCard.token == ref).first()
    if card is None:
        raise _api_error(404, "TARGET_NOT_FOUND", "Share card not found")
    return card.id


@router.post("/api/v2/reports", response_model=ReportOut, status_code=201)
def create_report(req: ReportCreate, db: Session = Depends(get_db),
                        token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    if req.target_type not in REPORT_TARGETS:
        raise _api_error(422, "INVALID_TARGET", f"target_type must be one of {', '.join(REPORT_TARGETS)}")
    if req.reason not in REPORT_REASONS:
        raise _api_error(422, "INVALID_REASON", f"reason must be one of {', '.join(REPORT_REASONS)}")
    target_id = _resolve_target(db, req)
    if req.target_type == "user" and target_id == uid:
        raise _api_error(422, "SELF_REPORT", "You cannot report yourself")
    existing = db.query(models.Report).filter(
        models.Report.reporter_id == uid, models.Report.target_type == req.target_type,
        models.Report.target_id == target_id).first()
    if existing is not None:
        return ReportOut(id=existing.id, target_type=existing.target_type, reason=existing.reason,
                         status=existing.status, created_at=existing.created_at,
                         message="You already reported this. Our team will review it.")
    today = db.query(models.Report).filter(
        models.Report.reporter_id == uid, models.Report.created_at >= _now_naive_utc() - timedelta(days=1)).count()
    if today >= MAX_REPORTS_PER_DAY:
        raise _api_error(429, "REPORT_LIMIT", "You have sent a lot of reports today. Please try again tomorrow.")
    report = models.Report(reporter_id=uid, target_type=req.target_type, target_id=target_id,
                           reason=req.reason, details=req.details)
    db.add(report)
    db.flush()
    _audit(db, actor_type="player", actor_id=uid, action="report.created", entity_type="report",
           entity_id=report.id, details={"target_type": req.target_type, "target_id": target_id,
                                         "reason": req.reason})
    message = "Thanks. Our team will review this report."
    if req.target_type == "challenge" and req.reason == "unsafe_route":
        unsafe = db.query(models.Report).filter(
            models.Report.target_type == "challenge", models.Report.target_id == target_id,
            models.Report.reason == "unsafe_route", models.Report.status == "open").count()
        ch = db.query(models.Challenge).filter(models.Challenge.id == target_id).first()
        if unsafe >= UNSAFE_ROUTE_AUTO_SUSPEND and ch.status == "open":
            ch.status = "suspended"
            ch.status_reason = "Paused automatically after safety reports; awaiting review"
            _audit(db, actor_type="system", actor_id=None, action="challenge.auto_suspended",
                   entity_type="challenge", entity_id=ch.id, details={"unsafe_reports": unsafe})
            message = "Thanks. This challenge has been paused while our team checks the route."
    db.commit()
    return ReportOut(id=report.id, target_type=report.target_type, reason=report.reason,
                     status=report.status, created_at=report.created_at, message=message)


@router.get("/api/v2/me/reports", response_model=List[ReportOut])
def my_reports(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    rows = db.query(models.Report).filter(models.Report.reporter_id == token_data["id"]).order_by(
        models.Report.created_at.desc()).limit(100).all()
    return [ReportOut(id=r.id, target_type=r.target_type, reason=r.reason, status=r.status,
                      created_at=r.created_at,
                      message="Under review" if r.status == "open" else (r.resolution_note or "Reviewed"))
            for r in rows]


# --- blocking --------------------------------------------------------------------

@router.post("/api/v2/blocks", response_model=BlockOut, status_code=201)
def block_player(req: BlockCreate, db: Session = Depends(get_db),
                       token_data: dict = Depends(get_active_player)):
    """Block by public handle, or block the creator of a challenge without learning who
    they are."""
    uid = token_data["id"]
    target: Optional[int] = None
    if req.handle:
        p = db.query(models.PlayerProfile).filter(models.PlayerProfile.referral_code == req.handle.upper()).first()
        target = p.user_id if p else None
    elif req.challenge_id is not None:
        ch = db.query(models.Challenge).filter(models.Challenge.id == req.challenge_id).first()
        target = ch.creator_id if ch else None
    if target is None:
        raise _api_error(404, "TARGET_NOT_FOUND", "Player not found")
    if target == uid:
        raise _api_error(422, "SELF_BLOCK", "You cannot block yourself")
    block = db.query(models.UserBlock).filter(
        models.UserBlock.blocker_id == uid, models.UserBlock.blocked_id == target).first()
    if block is None:
        block = models.UserBlock(blocker_id=uid, blocked_id=target)
        db.add(block)
        db.flush()
        _audit(db, actor_type="player", actor_id=uid, action="block.created", entity_type="user", entity_id=target)
    db.commit()
    return BlockOut(id=block.id, name=_blocked_name(db, block, 1), created_at=block.created_at)


def _blocked_name(db: Session, block: models.UserBlock, n: int) -> str:
    p = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == block.blocked_id).first()
    if p is not None and (p.public_profile or p.leaderboard_opt_in):
        return p.display_name
    return f"Blocked runner {n}"


@router.get("/api/v2/me/blocks", response_model=List[BlockOut])
def my_blocks(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    rows = db.query(models.UserBlock).filter(models.UserBlock.blocker_id == token_data["id"]).order_by(
        models.UserBlock.created_at.asc()).all()
    return [BlockOut(id=b.id, name=_blocked_name(db, b, i), created_at=b.created_at) for i, b in enumerate(rows, 1)]


@router.delete("/api/v2/blocks/{block_id}", status_code=204)
def unblock_player(block_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    block = db.query(models.UserBlock).filter(models.UserBlock.id == block_id).first()
    if block is None or block.blocker_id != token_data["id"]:
        raise _api_error(404, "BLOCK_NOT_FOUND", "Block not found")
    db.delete(block)
    db.commit()


# --- sessions and password ---------------------------------------------------------

@router.post("/api/v2/me/sessions/revoke", response_model=TokenOut)
def revoke_all_sessions(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Sign out everywhere. Returns a fresh token so this device stays signed in."""
    user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
    revoke_sessions(user)
    _audit(db, actor_type="player", actor_id=user.id, action="sessions.revoked", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(access_token=create_access_token({"sub": str(user.id), "role": "player"}),
                    message="Signed out of every other device.")


@router.post("/api/v2/me/password", response_model=TokenOut)
def change_password(req: PasswordChange, db: Session = Depends(get_db),
                          token_data: dict = Depends(get_active_player)):
    user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
    if not verify_password(req.current_password, user.hashed_password):
        raise _api_error(403, "WRONG_PASSWORD", "Your current password is not correct")
    user.hashed_password = get_password_hash(req.new_password)
    revoke_sessions(user)
    _audit(db, actor_type="player", actor_id=user.id, action="password.changed", entity_type="user", entity_id=user.id)
    db.commit()
    return TokenOut(access_token=create_access_token({"sub": str(user.id), "role": "player"}),
                    message="Password changed. Other devices have been signed out.")


# --- data rights (PRD-009) ---------------------------------------------------------

def _rows(query, fields: tuple) -> list:
    return [{f: getattr(r, f) for f in fields} for r in query.all()]


@router.get("/api/v2/me/export")
def export_my_data(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Everything Osiris holds about the player, including raw route points, as JSON."""
    uid = token_data["id"]
    user = db.query(models.User).filter(models.User.id == uid).first()
    profile = get_or_create_profile(db, user)
    db.commit()
    runs = db.query(models.RunSession).filter(models.RunSession.user_id == uid).order_by(models.RunSession.id).all()
    run_ids = [r.id for r in runs] or [-1]
    points: dict[int, list] = {}
    for p in db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).order_by(
            models.RoutePoint.run_session_id, models.RoutePoint.sequence).all():
        points.setdefault(p.run_session_id, []).append(
            {"t_ms": p.t_ms, "lat": p.lat, "lng": p.lng, "accuracy_m": p.accuracy_m})
    decisions = {d.run_session_id: d for d in db.query(models.VerificationDecision).filter(
        models.VerificationDecision.run_session_id.in_(run_ids)).all()}
    data = {
        "exported_at": _now_naive_utc().isoformat(),
        "policy_version": POLICY_VERSION,
        "account": {"id": user.id, "email": user.email, "xp": user.xp, "rank": user.rank,
                    "created_via": "v2" if profile.consent_required else "v1"},
        "profile": {"display_name": profile.display_name, "goal": profile.goal, "city": profile.city,
                    "public_profile": profile.public_profile, "leaderboard_opt_in": profile.leaderboard_opt_in,
                    "location_consent_at": profile.location_consent_at, "referral_code": profile.referral_code,
                    "utc_offset_minutes": profile.utc_offset_minutes},
        "runs": [{"id": r.id, "status": r.status, "verification_status": r.verification_status,
                  "started_at": r.started_at, "finished_at": r.finished_at, "distance_m": r.distance_m,
                  "duration_seconds": r.duration_seconds,
                  "verification_reasons": json.loads(decisions[r.id].reason_codes_json) if r.id in decisions else [],
                  "route_points": points.get(r.id, [])} for r in runs],
        "courses": [{"id": c.id, "name": c.name, "status": c.status, "distance_m": c.distance_m,
                     "route": json.loads(c.route_json or "[]")}
                    for c in db.query(models.Course).filter(models.Course.owner_id == uid).all()],
        "challenges_created": _rows(db.query(models.Challenge).filter(models.Challenge.creator_id == uid),
                                    ("id", "title", "status", "opens_at", "closes_at")),
        "challenge_attempts": _rows(db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.user_id == uid),
                                    ("challenge_id", "status", "outcome", "elapsed_seconds", "xp_awarded", "joined_at")),
        "badges": _rows(db.query(models.UserBadge).filter(models.UserBadge.user_id == uid), ("badge_code", "awarded_at")),
        "quest_awards": _rows(db.query(models.QuestAward).filter(models.QuestAward.user_id == uid),
                              ("quest_key", "xp_awarded", "awarded_at")),
        "share_cards": _rows(db.query(models.ShareCard).filter(models.ShareCard.user_id == uid),
                             ("token", "kind", "headline", "revoked_at", "created_at")),
        "communities": _rows(db.query(models.CommunityMember).filter(models.CommunityMember.user_id == uid),
                             ("community_id", "role", "joined_at")),
        "season_entries": _rows(db.query(models.SeasonEntry).filter(models.SeasonEntry.user_id == uid),
                                ("season_id", "joined_at")),
        "consents": _rows(db.query(models.ConsentRecord).filter(models.ConsentRecord.user_id == uid),
                          ("kind", "granted", "policy_version", "created_at")),
        "reports_filed": _rows(db.query(models.Report).filter(models.Report.reporter_id == uid),
                               ("target_type", "reason", "status", "created_at")),
        "blocks": _rows(db.query(models.UserBlock).filter(models.UserBlock.blocker_id == uid), ("created_at",)),
        "analytics_events": _rows(db.query(models.AnalyticsEvent).filter(models.AnalyticsEvent.user_id == uid),
                                  ("event_name", "occurred_at")),
    }
    return json.loads(json.dumps(data, default=str))


def erase_player(db: Session, user: models.User, actor_type: str, actor_id: Optional[int]) -> None:
    """Remove a player's personal data. The users row stays as an anonymous tombstone so
    challenges, results, and ledgers that reference it remain consistent for others."""
    uid = user.id
    now = _now_naive_utc()
    run_ids = [r for (r,) in db.query(models.RunSession.id).filter(models.RunSession.user_id == uid).all()] or [-1]
    db.query(models.RoutePoint).filter(models.RoutePoint.run_session_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(models.RunSession).filter(models.RunSession.id.in_(run_ids)).update(
        {models.RunSession.route_hash: None}, synchronize_session=False)
    tele_ids = [t for (t,) in db.query(models.TelemetrySession.id).filter(models.TelemetrySession.user_id == uid).all()] or [-1]
    db.query(models.TelemetryData).filter(models.TelemetryData.session_id.in_(tele_ids)).delete(synchronize_session=False)
    db.query(models.TelemetrySession).filter(models.TelemetrySession.id.in_(tele_ids)).delete(synchronize_session=False)
    db.query(models.ActivityLog).filter(models.ActivityLog.user_id == uid).delete(synchronize_session=False)
    for course in db.query(models.Course).filter(models.Course.owner_id == uid).all():
        course.status = "retired"
        course.route_json = "[]"
        course.start_lat = course.finish_lat = course.public_lat
        course.start_lng = course.finish_lng = course.public_lng
    # Open challenges close now; joined players keep the normal submission grace period.
    for ch in db.query(models.Challenge).filter(models.Challenge.creator_id == uid,
                                                models.Challenge.status == "open").all():
        ch.closes_at = now
    db.query(models.UserBadge).filter(models.UserBadge.user_id == uid).delete(synchronize_session=False)
    db.query(models.UserBlock).filter(
        (models.UserBlock.blocker_id == uid) | (models.UserBlock.blocked_id == uid)).delete(synchronize_session=False)
    db.query(models.Report).filter(models.Report.reporter_id == uid).update(
        {models.Report.reporter_id: None}, synchronize_session=False)
    db.query(models.ConsentRecord).filter(models.ConsentRecord.user_id == uid).delete(synchronize_session=False)
    delete_growth_data(db, [uid])
    user.email = f"deleted-{uid}-{secrets.token_hex(4)}@deleted.invalid"
    user.hashed_password = get_password_hash(secrets.token_urlsafe(32))
    user.xp = 0
    user.rank = get_rank(0)
    user.bmi = None
    user.suspended_at = now
    user.suspension_reason = "erased"
    revoke_sessions(user)
    _audit(db, actor_type=actor_type, actor_id=actor_id, action="player.erased", entity_type="user", entity_id=uid)


@router.post("/api/v2/me/erase", status_code=202)
def erase_my_account(req: EraseRequest, db: Session = Depends(get_db),
                           token_data: dict = Depends(get_active_player)):
    """Permanently erase the account. Needs the password and the word DELETE."""
    user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
    if req.confirm != ERASE_CONFIRMATION:
        raise _api_error(422, "CONFIRMATION_REQUIRED", "Type DELETE to confirm")
    if not verify_password(req.password, user.hashed_password):
        raise _api_error(403, "WRONG_PASSWORD", "Your password is not correct")
    erase_player(db, user, "player", user.id)
    db.commit()
    return {"status": "erased", "message": "Your account and personal data have been erased."}


# --- rules -----------------------------------------------------------------------

@router.get("/api/v2/rules")
def rules():
    """Plain-language rules shown in the app before a player relies on them. Public."""
    return {
        "policy_version": POLICY_VERSION,
        "rewards": [
            "Rewards in this release are XP, badges, and rank. They have no cash value.",
            "Challenges are free. There are no entry fees, stakes, or prizes, so there is nothing to refund.",
            "Partner perks (a discount or guest pass) are offered by that partner, who sets the terms.",
            "XP from a result later found to break the rules can be removed after review.",
        ],
        "referrals": [
            f"You earn {REFERRAL_XP} XP when a friend you invited completes a verified run of at least "
            f"{REFERRAL_MIN_DISTANCE_M // 1000} km.",
            f"Up to {REFERRAL_CAP} rewarded friends every 30 days. Accounts from your own device don't count.",
        ],
        "verification": [
            "Osiris checks each run's GPS route for realistic speed, gaps, accuracy, and timing.",
            "Unusually fast challenge results are checked by a person before they count.",
            "Verification uses rules, not AI, and it cannot catch everything. Report anything that looks wrong.",
        ],
        "leaderboards": [lb.SCORING_EXPLAINER,
                         "Your name appears only if you turn on leaderboard visibility."],
        "privacy": [
            "Public maps show challenges as approximate markers, never exact start or finish points.",
            "The first and last 150 m of a run are removed before it becomes a course.",
            "You can download or erase your data at any time from Settings.",
        ],
        "safety": [quest_rules.SAFETY_NOTE,
                   "Report an unsafe route. After three reports it is paused until our team checks it."],
    }


# --- admin abuse review ----------------------------------------------------------------

def _target_summary(db: Session, target_type: str, target_id: int) -> str:
    if target_type == "challenge":
        ch = db.query(models.Challenge).filter(models.Challenge.id == target_id).first()
        return f"Challenge #{target_id}: {ch.title} ({ch.status})" if ch else f"Challenge #{target_id}"
    if target_type == "user":
        p = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == target_id).first()
        return f"Player #{target_id}: {p.display_name}" if p else f"Player #{target_id}"
    if target_type == "community":
        c = db.query(models.Community).filter(models.Community.id == target_id).first()
        return f"Community #{target_id}: {c.name} ({c.status})" if c else f"Community #{target_id}"
    card = db.query(models.ShareCard).filter(models.ShareCard.id == target_id).first()
    return f"Share card #{target_id}: {card.headline}" if card else f"Share card #{target_id}"


@router.get("/api/v2/admin/reports", response_model=List[AdminReportItem])
def admin_reports(status: str = "open", db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    rows = db.query(models.Report).filter(models.Report.status == status).order_by(
        models.Report.created_at.asc()).limit(500).all()
    out = []
    for r in rows:
        open_count = db.query(models.Report).filter(
            models.Report.target_type == r.target_type, models.Report.target_id == r.target_id,
            models.Report.status == "open").count()
        out.append(AdminReportItem(
            id=r.id, target_type=r.target_type, target_id=r.target_id,
            target_summary=_target_summary(db, r.target_type, r.target_id), reason=r.reason,
            details=r.details, status=r.status, open_reports_on_target=open_count, created_at=r.created_at))
    return out


@router.post("/api/v2/admin/reports/{report_id}/resolve")
def admin_resolve_report(report_id: int, req: AdminReportResolve, db: Session = Depends(get_db),
                               admin: dict = Depends(get_current_admin)):
    """Record the outcome. Enforcement (suspend a player, challenge, or community) uses the
    existing admin controls; this closes the reports and tells reporters it was reviewed."""
    if req.status not in ("actioned", "dismissed"):
        raise _api_error(422, "INVALID_STATUS", "status must be actioned or dismissed")
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if report is None:
        raise _api_error(404, "REPORT_NOT_FOUND", "Report not found")
    q = db.query(models.Report).filter(models.Report.id == report.id)
    if req.all_for_target:
        q = db.query(models.Report).filter(models.Report.target_type == report.target_type,
                                           models.Report.target_id == report.target_id,
                                           models.Report.status == "open")
    now = _now_naive_utc()
    resolved = 0
    for r in q.all():
        r.status = req.status
        r.resolution_note = req.note
        r.reviewed_by_admin_id = admin["id"]
        r.reviewed_at = now
        resolved += 1
    _audit(db, actor_type="admin", actor_id=admin["id"], action="report.resolved", entity_type="report",
           entity_id=report.id, details={"status": req.status, "resolved": resolved, "note": req.note})
    db.commit()
    return {"resolved": resolved, "status": req.status}


@router.post("/api/v2/admin/users/{user_id}/reset-display-name")
def admin_reset_display_name(user_id: int, req: AdminReason, db: Session = Depends(get_db),
                                   admin: dict = Depends(get_current_admin)):
    profile = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == user_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Player not found")
    profile.display_name = f"Runner {user_id}"
    _audit(db, actor_type="admin", actor_id=admin["id"], action="player.display_name_reset",
           entity_type="user", entity_id=user_id, details={"reason": req.reason})
    db.commit()
    return {"user_id": user_id, "display_name": profile.display_name}


@router.post("/api/v2/admin/users/{user_id}/erase", status_code=202)
def admin_erase_user(user_id: int, req: AdminReason, db: Session = Depends(get_db),
                           admin: dict = Depends(get_current_admin)):
    """Erase on a verified request received outside the app (e.g. by email)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Player not found")
    erase_player(db, user, "admin", admin["id"])
    db.commit()
    return {"status": "erased", "user_id": user_id}


app.include_router(router)
