"""Growth release endpoints: the core habit loop (G1).

"What is my next physical quest?" — registration without body measurements, a goal-driven
daily quest, a weekly goal, a rest-friendly weekly streak, and funnel analytics.

`main.py` imports this module on its last line, so every name imported from `main` below
already exists whichever module is imported first. The router registers itself on
`main.app` at the bottom of this file, once all routes are declared.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case
from sqlalchemy.orm import Session

import models
import spatial_utils
from main import (
    _api_error,
    _audit,
    _challenge_public,
    _check_email_unique,
    _award_badge,
    _now_naive_utc,
    _refresh_challenge_status,
    _rl_onboard,
    app,
    ChallengePublic,
    create_access_token,
    get_active_player,
    get_current_admin,
    get_current_user_token,
    get_db,
    get_password_hash,
    get_rank,
    get_title,
)
from services import challenges as challenge_rules
from services import leaderboards as leaderboard_rules
from services import quests as quest_rules

router = APIRouter()

TAGLINE = "Fitness, turned into quests."

# Events a client may report. Everything else the server records itself, so a client
# cannot inflate the funnel steps that matter (verified runs, challenge results).
CLIENT_EVENTS = {
    "app_installed", "app_opened", "onboarding_viewed", "quest_viewed", "run_started",
    "share_opened", "share_completed", "invite_sent",
}
SERVER_EVENTS = {
    "account_created", "onboarding_completed", "first_verified_run", "verified_run",
    "daily_quest_completed", "weekly_goal_completed", "challenge_joined",
    "challenge_completed", "invite_accepted", "referral_rewarded", "share_created",
    "community_joined", "season_joined",
}
MAX_EVENT_PROPERTIES_BYTES = 1024
FORBIDDEN_PROPERTY_KEYS = {"lat", "lng", "latitude", "longitude", "email", "route"}
STARTER_CHALLENGE_RADIUS_KM = 5.0
HISTORY_LOOKBACK_DAYS = 26 * 7

# Referral rules (anti-cheat): the inviter is rewarded only after the friend completes a
# verified run of at least 1 km, never for the sign-up alone; a friend signing up from an
# install the inviter has used earns nothing; and each inviter can earn at most five
# rewards per 30 days. Rewards are XP and a badge only.
REFERRAL_MIN_DISTANCE_M = 1_000
REFERRAL_XP = 50
REFERRAL_CAP = 5
REFERRAL_CAP_WINDOW_DAYS = 30


# --- helpers ---------------------------------------------------------------------

def emit_event(
    db: Session, name: str, *, user_id: Optional[int] = None, install_id: Optional[str] = None,
    properties: Optional[dict] = None, source: str = "server", once: bool = False,
) -> bool:
    """Record a funnel event in the caller's transaction. With `once`, a user gets at
    most one row for this event name (first-X milestones). Returns True if written."""
    if once and user_id is not None:
        exists = db.query(models.AnalyticsEvent.id).filter(
            models.AnalyticsEvent.user_id == user_id, models.AnalyticsEvent.event_name == name,
        ).first()
        if exists:
            return False
    db.add(models.AnalyticsEvent(
        user_id=user_id, install_id=install_id, event_name=name, source=source,
        properties_json=json.dumps(properties or {}, sort_keys=True, default=str),
    ))
    return True


def _new_referral_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I confusion
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.query(models.PlayerProfile.id).filter(models.PlayerProfile.referral_code == code).first():
            return code
    raise RuntimeError("could not mint a unique referral code")


def get_or_create_profile(db: Session, user: models.User) -> models.PlayerProfile:
    """Players registered through legacy v1 onboarding get a profile on first use. The
    default display name never derives from the email address."""
    profile = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == user.id).first()
    if profile is None:
        profile = models.PlayerProfile(
            user_id=user.id, display_name=f"Runner {user.id}", goal=quest_rules.DEFAULT_GOAL,
            referral_code=_new_referral_code(db),
        )
        db.add(profile)
        db.flush()
    return profile


def _daily_totals(db: Session, user_id: int, utc_offset_minutes: int, now: datetime) -> dict:
    since = now - timedelta(days=HISTORY_LOOKBACK_DAYS)
    rows = (
        db.query(models.RunSession.finished_at, models.RunSession.distance_m)
        .filter(
            models.RunSession.user_id == user_id,
            models.RunSession.verification_status == "accepted",
            models.RunSession.finished_at.isnot(None),
            models.RunSession.finished_at >= since,
        )
        .all()
    )
    return quest_rules.daily_totals([(finished_at, distance) for finished_at, distance in rows], utc_offset_minutes)


def _grant_quest(
    db: Session, user: models.User, key: str, xp: int, *, target_m: Optional[int], run_id: Optional[int],
) -> bool:
    if db.query(models.QuestAward.id).filter(
        models.QuestAward.user_id == user.id, models.QuestAward.quest_key == key,
    ).first():
        return False
    db.add(models.QuestAward(
        user_id=user.id, quest_key=key, rules_version=quest_rules.QUEST_RULES_VERSION,
        target_m=target_m, xp_awarded=xp, run_session_id=run_id,
    ))
    user.xp = (user.xp or 0) + xp
    user.rank = get_rank(user.xp, user.last_activity_date)
    return True


def on_run_accepted(db: Session, user: models.User, session: models.RunSession) -> dict:
    """Hook called by `/api/v2/runs/{id}/finish` after a run is accepted, inside its
    transaction. Grants any daily quest / weekly goal the run completed and records the
    funnel milestones. Returns {"quest_xp": int, "quests": [keys]}."""
    db.flush()
    profile = get_or_create_profile(db, user)
    offset = profile.utc_offset_minutes or 0
    now = session.finished_at or _now_naive_utc()
    totals = _daily_totals(db, user.id, offset, now)
    today = quest_rules.local_date(now, offset)

    granted: list[str] = []
    xp = 0
    quest = quest_rules.daily_quest(profile.goal, today, totals)
    _, done = quest_rules.quest_progress(quest, totals)
    if done and _grant_quest(db, user, quest.key, quest.xp, target_m=quest.target_m, run_id=session.id):
        granted.append(quest.key)
        xp += quest.xp
        emit_event(db, "daily_quest_completed", user_id=user.id,
                   properties={"kind": quest.kind, "target_m": quest.target_m})
        _award_badge(db, user.id, "FIRST_DAILY_QUEST")
    week = quest_rules.weekly_goal(profile.goal, today, totals)
    if week.completed and _grant_quest(db, user, week.key, week.xp, target_m=None, run_id=session.id):
        granted.append(week.key)
        xp += week.xp
        emit_event(db, "weekly_goal_completed", user_id=user.id,
                   properties={"active_days": week.active_days})
        _award_badge(db, user.id, "FIRST_WEEKLY_GOAL")
    _settle_referral(db, profile, session)

    emit_event(db, "first_verified_run", user_id=user.id, once=True)
    emit_event(db, "verified_run", user_id=user.id,
               properties={"distance_band_km": int((session.distance_m or 0) // 1000)})
    return {"quest_xp": xp, "quests": granted}


def delete_growth_data(db: Session, user_ids: list[int]) -> None:
    """Erase a player's growth rows (profile, quest awards, funnel events) before the user
    row goes. Other players' referral links to them are cleared, not deleted."""
    if not user_ids:
        return
    db.query(models.QuestAward).filter(models.QuestAward.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.AnalyticsEvent).filter(models.AnalyticsEvent.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.PlayerProfile).filter(models.PlayerProfile.referred_by_user_id.in_(user_ids)).update(
        {models.PlayerProfile.referred_by_user_id: None}, synchronize_session=False)
    db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.ShareCard).filter(models.ShareCard.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.ChallengeInvite).filter(models.ChallengeInvite.inviter_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.SeasonEntry).filter(models.SeasonEntry.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.ConsentRecord).filter(models.ConsentRecord.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.UserBlock).filter(
        models.UserBlock.blocker_id.in_(user_ids) | models.UserBlock.blocked_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(models.Report).filter(models.Report.reporter_id.in_(user_ids)).update(
        {models.Report.reporter_id: None}, synchronize_session=False)
    db.query(models.CommunityMember).filter(models.CommunityMember.user_id.in_(user_ids)).delete(synchronize_session=False)
    # A deleted owner hands the community to its longest-standing remaining member; an
    # empty community is removed with its featured-challenge links.
    for community in db.query(models.Community).filter(models.Community.owner_user_id.in_(user_ids)).all():
        heir = (db.query(models.CommunityMember)
                .filter(models.CommunityMember.community_id == community.id)
                .order_by(case((models.CommunityMember.role == "admin", 0), else_=1),
                          models.CommunityMember.joined_at.asc()).first())
        if heir is not None:
            community.owner_user_id = heir.user_id
            heir.role = "owner"
        else:
            db.query(models.CommunityChallenge).filter(
                models.CommunityChallenge.community_id == community.id).delete(synchronize_session=False)
            db.delete(community)
    db.query(models.CommunityChallenge).filter(models.CommunityChallenge.added_by_user_id.in_(user_ids)).delete(
        synchronize_session=False)


def _inviter_install_ids(db: Session, inviter: models.PlayerProfile) -> set[str]:
    ids = {
        i for (i,) in db.query(models.AnalyticsEvent.install_id)
        .filter(models.AnalyticsEvent.user_id == inviter.user_id, models.AnalyticsEvent.install_id.isnot(None))
        .distinct().all()
    }
    if inviter.signup_install_id:
        ids.add(inviter.signup_install_id)
    return ids


def _settle_referral(db: Session, profile: models.PlayerProfile, session: models.RunSession) -> None:
    """Grant the inviter's reward once the referred player has a qualifying verified run."""
    if profile.referral_status != "pending" or profile.referred_by_user_id is None:
        return
    if (session.distance_m or 0) < REFERRAL_MIN_DISTANCE_M:
        return
    inviter = db.query(models.PlayerProfile).filter(
        models.PlayerProfile.user_id == profile.referred_by_user_id,
    ).first()
    inviter_user = db.query(models.User).filter(models.User.id == profile.referred_by_user_id).first()
    if inviter is None or inviter_user is None:
        profile.referral_status = "none"
        return
    if profile.signup_install_id and profile.signup_install_id in _inviter_install_ids(db, inviter):
        profile.referral_status = "same_device"
        _audit(db, actor_type="system", actor_id=None, action="referral.refused_same_device",
               entity_type="user", entity_id=profile.user_id, details={"inviter_id": inviter.user_id})
        return
    since = _now_naive_utc() - timedelta(days=REFERRAL_CAP_WINDOW_DAYS)
    recent = db.query(models.PlayerProfile).filter(
        models.PlayerProfile.referred_by_user_id == inviter.user_id,
        models.PlayerProfile.referral_status == "rewarded",
        models.PlayerProfile.referral_rewarded_at >= since,
    ).count()
    _award_badge(db, profile.user_id, "WELCOMED")
    if recent >= REFERRAL_CAP:
        profile.referral_status = "capped"
        return
    profile.referral_status = "rewarded"
    profile.referral_rewarded_at = _now_naive_utc()
    inviter_user.xp = (inviter_user.xp or 0) + REFERRAL_XP
    inviter_user.rank = get_rank(inviter_user.xp, inviter_user.last_activity_date)
    _award_badge(db, inviter.user_id, "RECRUITER")
    emit_event(db, "referral_rewarded", user_id=inviter.user_id, properties={"referee_id": profile.user_id})
    _audit(db, actor_type="system", actor_id=None, action="referral.rewarded",
           entity_type="user", entity_id=inviter.user_id,
           details={"referee_id": profile.user_id, "xp": REFERRAL_XP})


def optional_token(authorization: Optional[str] = Header(default=None)) -> Optional[dict]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return get_current_user_token(authorization.split(" ", 1)[1])


# --- schemas ---------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=30)
    goal: str = Field(default=quest_rules.DEFAULT_GOAL)
    referral_code: Optional[str] = Field(default=None, max_length=16)
    # A challenge invite link token; implies the inviter's referral code.
    invite_token: Optional[str] = Field(default=None, max_length=64)
    install_id: Optional[str] = Field(default=None, max_length=64)
    utc_offset_minutes: int = Field(default=0, ge=-840, le=840)
    # The consent screen is part of sign-up; runs are refused until this is granted.
    location_consent: bool = False


class ProfileOut(BaseModel):
    user_id: int
    display_name: str
    goal: str
    identity: str
    public_profile: bool
    location_consent: bool
    onboarding_completed: bool
    referral_code: str
    utc_offset_minutes: int
    city: Optional[str] = None
    leaderboard_opt_in: bool = False


class RegisterResponse(BaseModel):
    access_token: str
    role: str = "player"
    profile: ProfileOut


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=30)
    goal: Optional[str] = None
    public_profile: Optional[bool] = None
    location_consent: Optional[bool] = None
    onboarding_completed: Optional[bool] = None
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-840, le=840)
    city: Optional[str] = Field(default=None, max_length=60)
    leaderboard_opt_in: Optional[bool] = None


class QuestOut(BaseModel):
    key: str
    kind: str
    title: str
    description: str
    target_m: int
    xp: int
    optional: bool
    progress_m: float = 0.0
    completed: bool = False
    rewarded: bool = False


class WeeklyOut(BaseModel):
    key: str
    week_start: str
    active_days_target: int
    active_days: int
    distance_m: float
    xp: int
    completed: bool
    rewarded: bool


class TodayResponse(BaseModel):
    tagline: str
    display_name: str
    identity: str
    goal: str
    xp: int
    performance_rank: str
    rules_version: str
    today: QuestOut
    tomorrow: QuestOut
    week: WeeklyOut
    streak_weeks: int
    starter_challenge: Optional[ChallengePublic] = None
    safety_note: str
    needs_location_consent: bool = False


class EventIn(BaseModel):
    event_name: str
    install_id: Optional[str] = Field(default=None, max_length=64)
    properties: dict[str, Any] = Field(default_factory=dict)


class FunnelStep(BaseModel):
    step: str
    users: int
    rate_from_previous: Optional[float] = None


class FunnelResponse(BaseModel):
    window_days: int
    installs: int
    steps: List[FunnelStep]
    week1_retention: Optional[float]
    week4_retention: Optional[float]
    inviters: int
    challenges_joined: int
    challenges_completed: int
    challenge_completion_rate: Optional[float]


def _profile_out(profile: models.PlayerProfile) -> ProfileOut:
    return ProfileOut(
        user_id=profile.user_id, display_name=profile.display_name, goal=profile.goal,
        identity=quest_rules.identity_for(profile.goal), public_profile=bool(profile.public_profile),
        location_consent=profile.location_consent_at is not None,
        onboarding_completed=profile.onboarding_completed_at is not None,
        referral_code=profile.referral_code, utc_offset_minutes=profile.utc_offset_minutes or 0,
        city=profile.city, leaderboard_opt_in=bool(profile.leaderboard_opt_in),
    )


def _validate_goal(goal: Optional[str]) -> None:
    if goal is not None and goal not in quest_rules.GOALS:
        raise _api_error(422, "INVALID_GOAL", f"goal must be one of {', '.join(quest_rules.GOALS)}")


def _load_user(db: Session, user_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return user


# --- endpoints -------------------------------------------------------------------

@router.post("/api/v2/auth/register", response_model=RegisterResponse, status_code=201)
async def register_player(req: RegisterRequest, db: Session = Depends(get_db), _rl: None = Depends(_rl_onboard)):
    """Plain registration: email, password, a display name, and a goal. No weight, height,
    or BMI. A referral code links the account to the inviter; the inviter's reward waits
    until this player completes a verified run (see G2 referral rules)."""
    _validate_goal(req.goal)
    email = req.email.strip().lower()
    if "@" not in email:
        raise _api_error(422, "INVALID_EMAIL", "Enter a valid email address")
    _check_email_unique(db, email)

    referrer: Optional[models.PlayerProfile] = None
    invite: Optional[models.ChallengeInvite] = None
    if req.invite_token:
        invite = db.query(models.ChallengeInvite).filter(models.ChallengeInvite.token == req.invite_token).first()
        if invite is None:
            raise _api_error(404, "INVITE_NOT_FOUND", "That invite link was not found")
        referrer = db.query(models.PlayerProfile).filter(
            models.PlayerProfile.user_id == invite.inviter_id,
        ).first()
    elif req.referral_code:
        referrer = db.query(models.PlayerProfile).filter(
            models.PlayerProfile.referral_code == req.referral_code.strip().upper(),
        ).first()
        if referrer is None:
            raise _api_error(404, "REFERRAL_NOT_FOUND", "That invite code was not found")

    now = _now_naive_utc()
    user = models.User(
        email=email, hashed_password=get_password_hash(req.password), bmi=None,
        avatar_class=quest_rules.identity_for(req.goal).title(), xp=0, rank=get_rank(0),
        title=get_title(0.0), cumulative_area=0.0, last_activity_date=now, streak=0,
        # Simpler first economy: no opening crystal grant for v2 accounts, so the ledger
        # invariant holds with zero rows.
        mana_crystals=0,
    )
    db.add(user)
    db.flush()
    profile = models.PlayerProfile(
        user_id=user.id, display_name=req.display_name.strip(), goal=req.goal,
        utc_offset_minutes=req.utc_offset_minutes, referral_code=_new_referral_code(db),
        referred_by_user_id=referrer.user_id if referrer else None,
        referral_status="pending" if referrer else "none",
        signup_install_id=req.install_id,
        consent_required=True,
        location_consent_at=now if req.location_consent else None,
    )
    db.add(profile)
    if req.location_consent:
        growth_safety.record_consent(db, user.id, "location", True)
    if invite is not None:
        invite.signups = (invite.signups or 0) + 1
    emit_event(db, "account_created", user_id=user.id, install_id=req.install_id,
               properties={"goal": req.goal, "referred": referrer is not None})
    if referrer:
        emit_event(db, "invite_accepted", user_id=referrer.user_id,
                   properties={"referee_id": user.id})
    _audit(db, actor_type="player", actor_id=user.id, action="player.registered",
           entity_type="user", entity_id=user.id, details={"referred": referrer is not None})
    db.commit()
    db.refresh(profile)
    return RegisterResponse(
        access_token=create_access_token({"sub": str(user.id), "role": "player"}),
        profile=_profile_out(profile),
    )


@router.get("/api/v2/me/profile", response_model=ProfileOut)
async def get_my_profile(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    user = _load_user(db, token_data["id"])
    profile = get_or_create_profile(db, user)
    db.commit()
    return _profile_out(profile)


@router.put("/api/v2/me/profile", response_model=ProfileOut)
async def update_my_profile(
    req: ProfileUpdate, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    _validate_goal(req.goal)
    user = _load_user(db, token_data["id"])
    profile = get_or_create_profile(db, user)
    now = _now_naive_utc()
    if req.display_name is not None:
        profile.display_name = req.display_name.strip()
    if req.goal is not None:
        profile.goal = req.goal
        user.avatar_class = quest_rules.identity_for(req.goal).title()
    if req.public_profile is not None and req.public_profile != bool(profile.public_profile):
        profile.public_profile = req.public_profile
        growth_safety.record_consent(db, user.id, "public_profile", req.public_profile)
    if req.utc_offset_minutes is not None:
        profile.utc_offset_minutes = req.utc_offset_minutes
    if req.city is not None:
        profile.city = leaderboard_rules.slugify(req.city) if req.city.strip() else None
    if req.leaderboard_opt_in is not None and req.leaderboard_opt_in != bool(profile.leaderboard_opt_in):
        profile.leaderboard_opt_in = req.leaderboard_opt_in
        growth_safety.record_consent(db, user.id, "leaderboard", req.leaderboard_opt_in)
    if req.location_consent is not None and req.location_consent != (profile.location_consent_at is not None):
        profile.location_consent_at = now if req.location_consent else None
        growth_safety.record_consent(db, user.id, "location", req.location_consent)
        _audit(db, actor_type="player", actor_id=user.id,
               action="consent.location." + ("granted" if req.location_consent else "withdrawn"),
               entity_type="user", entity_id=user.id)
    if req.onboarding_completed and profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = now
        emit_event(db, "onboarding_completed", user_id=user.id, properties={"goal": profile.goal}, once=True)
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


def _quest_out(quest: quest_rules.DailyQuest, totals: dict, rewarded: bool) -> QuestOut:
    progress, done = quest_rules.quest_progress(quest, totals)
    return QuestOut(
        key=quest.key, kind=quest.kind, title=quest.title, description=quest.description,
        target_m=quest.target_m, xp=quest.xp, optional=quest.optional,
        progress_m=round(progress, 1), completed=done, rewarded=rewarded,
    )


def _starter_challenge(db: Session, lat: float, lng: float, viewer_id: int) -> Optional[ChallengePublic]:
    """The nearest open challenge the viewer has not joined, by generalized marker."""
    import math
    radius = STARTER_CHALLENGE_RADIUS_KM
    dlat = radius / 111.0
    dlng = radius / (111.0 * max(0.01, math.cos(math.radians(lat))))
    rows = (
        db.query(models.Challenge, models.Course)
        .join(models.Course, models.Course.id == models.Challenge.course_id)
        .filter(
            models.Challenge.status == "open",
            models.Course.status == "active",
            models.Challenge.creator_id != viewer_id,
            models.Course.public_lat.between(lat - dlat, lat + dlat),
            models.Course.public_lng.between(lng - dlng, lng + dlng),
        )
        .all()
    )
    hidden = growth_safety.blocked_user_ids(db, viewer_id)
    joined = {
        cid for (cid,) in db.query(models.ChallengeAttempt.challenge_id)
        .filter(models.ChallengeAttempt.user_id == viewer_id).all()
    }
    now = _now_naive_utc()
    best = None
    for ch, course in rows:
        _refresh_challenge_status(db, ch, now)
        if ch.status != "open" or ch.id in joined or ch.creator_id in hidden:
            continue
        dist = spatial_utils.haversine_distance(lat, lng, course.public_lat, course.public_lng)
        if dist <= radius and (best is None or dist < best[0]):
            best = (dist, ch, course)
    if best is None:
        return None
    dist, ch, course = best
    return _challenge_public(db, ch, course, viewer_id, distance_km=round(dist, 1))


@router.get("/api/v2/me/today", response_model=TodayResponse)
async def my_today(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    utc_offset_minutes: Optional[int] = None,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """The home screen in one call: today's quest, tomorrow's preview, the weekly goal,
    the weekly streak, and one nearby starter challenge when a location is supplied.
    The location is used for this lookup only and is not stored."""
    user = _load_user(db, token_data["id"])
    profile = get_or_create_profile(db, user)
    if utc_offset_minutes is not None and -840 <= utc_offset_minutes <= 840:
        profile.utc_offset_minutes = utc_offset_minutes
    offset = profile.utc_offset_minutes or 0
    now = _now_naive_utc()
    totals = _daily_totals(db, user.id, offset, now)
    today = quest_rules.local_date(now, offset)

    awarded = {
        k for (k,) in db.query(models.QuestAward.quest_key).filter(models.QuestAward.user_id == user.id).all()
    }
    quest = quest_rules.daily_quest(profile.goal, today, totals)
    # Tomorrow's preview assumes today's quest gets done if it has not been yet, so the
    # preview does not shrink just because the player hasn't gone out yet.
    projected = dict(totals)
    if projected.get(today, 0) < quest.target_m and not quest.optional:
        projected[today] = quest.target_m
    tomorrow = quest_rules.daily_quest(profile.goal, today + timedelta(days=1), projected)
    week = quest_rules.weekly_goal(profile.goal, today, totals)

    starter = None
    if lat is not None and lng is not None:
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise _api_error(422, "INVALID_LOCATION", "lat/lng out of range")
        starter = _starter_challenge(db, lat, lng, user.id)
    emit_event(db, "quest_viewed", user_id=user.id, properties={"kind": quest.kind})
    db.commit()

    xp = user.xp or 0
    return TodayResponse(
        tagline=TAGLINE, display_name=profile.display_name,
        identity=quest_rules.identity_for(profile.goal), goal=profile.goal, xp=xp,
        performance_rank=challenge_rules.performance_rank(xp),
        rules_version=quest_rules.QUEST_RULES_VERSION,
        today=_quest_out(quest, totals, quest.key in awarded),
        tomorrow=_quest_out(tomorrow, {}, False),
        week=WeeklyOut(
            key=week.key, week_start=week.week_start.isoformat(),
            active_days_target=week.active_days_target, active_days=week.active_days,
            distance_m=round(week.distance_m, 1), xp=week.xp, completed=week.completed,
            rewarded=week.key in awarded,
        ),
        streak_weeks=quest_rules.weekly_streak(profile.goal, today, totals),
        starter_challenge=starter,
        safety_note=quest_rules.SAFETY_NOTE,
        needs_location_consent=bool(profile.consent_required and profile.location_consent_at is None),
    )


@router.post("/api/v2/events", status_code=202)
async def track_event(
    event: EventIn, db: Session = Depends(get_db), token_data: Optional[dict] = Depends(optional_token),
):
    """Client funnel events (installs, app opens, shares). Anonymous events need an
    install id. Server-owned milestones are rejected here so they cannot be forged."""
    if event.event_name not in CLIENT_EVENTS:
        raise _api_error(422, "UNKNOWN_EVENT", "event_name is not a client event")
    user_id = token_data["id"] if token_data and token_data.get("role") == "player" else None
    if user_id is None and not event.install_id:
        raise _api_error(422, "INSTALL_ID_REQUIRED", "Anonymous events need an install_id")
    if FORBIDDEN_PROPERTY_KEYS & {k.lower() for k in event.properties}:
        raise _api_error(422, "FORBIDDEN_PROPERTY", "Event properties may not carry location or contact data")
    if len(json.dumps(event.properties, default=str)) > MAX_EVENT_PROPERTIES_BYTES:
        raise _api_error(422, "PROPERTIES_TOO_LARGE", "Event properties are limited to 1 KB")
    emit_event(db, event.event_name, user_id=user_id, install_id=event.install_id,
               properties=event.properties, source="client")
    db.commit()
    return {"accepted": True}


def _users_with(db: Session, name: str, cohort: set[int]) -> set[int]:
    if not cohort:
        return set()
    return {
        uid for (uid,) in db.query(models.AnalyticsEvent.user_id)
        .filter(models.AnalyticsEvent.event_name == name, models.AnalyticsEvent.user_id.in_(cohort))
        .distinct().all()
    }


def _rate(n: int, d: int) -> Optional[float]:
    return round(n / d, 4) if d else None


@router.get("/api/v2/admin/funnel", response_model=FunnelResponse)
async def admin_funnel(
    days: int = 90, db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin),
):
    """Activation funnel and retention for players who registered in the window.
    Week-N retention = share of the cohort (old enough to measure) with a verified run
    7N..7N+6 days after sign-up."""
    days = min(max(days, 1), 365)
    now = _now_naive_utc()
    since = now - timedelta(days=days)
    created = (
        db.query(models.AnalyticsEvent.user_id, models.AnalyticsEvent.occurred_at)
        .filter(models.AnalyticsEvent.event_name == "account_created",
                models.AnalyticsEvent.occurred_at >= since,
                models.AnalyticsEvent.user_id.isnot(None))
        .all()
    )
    signup_at = {uid: at for uid, at in created}
    cohort = set(signup_at)
    installs = (
        db.query(models.AnalyticsEvent.install_id)
        .filter(models.AnalyticsEvent.event_name == "app_installed", models.AnalyticsEvent.occurred_at >= since)
        .distinct().count()
    )

    onboarded = _users_with(db, "onboarding_completed", cohort)
    first_activity = _users_with(db, "run_started", cohort) | _users_with(db, "first_verified_run", cohort)
    verified = _users_with(db, "first_verified_run", cohort)
    joins = (
        db.query(models.AnalyticsEvent.user_id)
        .filter(models.AnalyticsEvent.event_name == "challenge_joined",
                models.AnalyticsEvent.user_id.in_(cohort or {-1}))
        .all()
    )
    join_counts: dict[int, int] = {}
    for (uid,) in joins:
        join_counts[uid] = join_counts.get(uid, 0) + 1
    second_challenge = {uid for uid, n in join_counts.items() if n >= 2 and uid in verified}

    ordered = [
        ("account_created", cohort), ("onboarding_completed", onboarded),
        ("first_activity", first_activity), ("first_verified_result", verified),
        ("second_challenge", second_challenge),
    ]
    steps: List[FunnelStep] = []
    prev = None
    for name, users in ordered:
        steps.append(FunnelStep(step=name, users=len(users),
                                rate_from_previous=_rate(len(users), prev) if prev is not None else None))
        prev = len(users)

    def retention(week: int) -> Optional[float]:
        eligible = {u for u, at in signup_at.items() if at + timedelta(days=7 * week + 7) <= now}
        if not eligible:
            return None
        active = 0
        for uid in eligible:
            start = signup_at[uid] + timedelta(days=7 * week)
            if db.query(models.RunSession.id).filter(
                models.RunSession.user_id == uid, models.RunSession.verification_status == "accepted",
                models.RunSession.finished_at >= start, models.RunSession.finished_at < start + timedelta(days=7),
            ).first():
                active += 1
        return _rate(active, len(eligible))

    inviters = (
        db.query(models.PlayerProfile.referred_by_user_id)
        .filter(models.PlayerProfile.referred_by_user_id.in_(cohort or {-1}))
        .distinct().count()
    )
    joined_total = db.query(models.AnalyticsEvent).filter(
        models.AnalyticsEvent.event_name == "challenge_joined", models.AnalyticsEvent.occurred_at >= since,
    ).count()
    completed_total = db.query(models.AnalyticsEvent).filter(
        models.AnalyticsEvent.event_name == "challenge_completed", models.AnalyticsEvent.occurred_at >= since,
    ).count()
    return FunnelResponse(
        window_days=days, installs=installs, steps=steps,
        week1_retention=retention(1), week4_retention=retention(4),
        inviters=inviters, challenges_joined=joined_total, challenges_completed=completed_total,
        challenge_completion_rate=_rate(completed_total, joined_total),
    )


app.include_router(router)

# Later growth modules build on this one, so they load after it is complete. Importing them
# here (not from main) keeps every import order working: main -> growth_api -> growth_social.
import growth_social  # noqa: E402,F401
import growth_communities  # noqa: E402,F401
import growth_safety  # noqa: E402
