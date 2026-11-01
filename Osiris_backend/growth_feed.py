# ruff: noqa: B008, B904
"""Home screen social feed, notifications, suggested global challenges, and suggested/trending Osirians.

Endpoints:
  - GET  /api/v2/me/notifications
  - POST /api/v2/me/notifications/{notification_id}/read
  - POST /api/v2/me/notifications/read-all
  - GET  /api/v2/challenges/suggested
  - GET  /api/v2/osirians/suggested
  - GET  /api/v2/osirians/trending
  - POST /api/v2/osirians/{user_id}/follow
  - DELETE /api/v2/osirians/{user_id}/follow
  - POST /api/v2/osirians/{user_id}/dismiss
  - GET  /api/v2/feed/posts
  - POST /api/v2/feed/posts
  - POST /api/v2/feed/posts/{post_id}/react
  - GET  /api/v2/feed/posts/{post_id}/comments
  - POST /api/v2/feed/posts/{post_id}/comments
  - POST /api/v2/feed/posts/{post_id}/share
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import settings
from core.clock import _now_naive_utc
from core.errors import _api_error
from core.security import get_active_player
from database import get_db
from growth_api import get_or_create_profile
from services import challenges as challenge_rules
from services import exercises as exercise_rules
from services import player_safety
from services import quests as quest_rules
from services.challenge_store import ChallengeStats, _refresh_challenge_status

router = APIRouter()

POST_KINDS = ("workout", "run", "domain_claim", "streak", "crystal_earn", "custom")
REACTION_KINDS = ("fire", "like", "clap", "crown")

SYSTEM_WELCOME_NOTIFICATIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "feature_suggestion",
        "New: Camera-Verified Multi-Set Workouts",
        "Customize your Streak Start workout (e.g. Push-ups 10 x 3, Squats 15 x 3, Plank holds) with live on-device AI pose tracking.",
        "exercise",
    ),
    (
        "app_update",
        "Global Challenges & People's Posts Live",
        "Swipe the circular Suggested Challenges deck to join global challenges from anywhere, follow trending Osirians, and share your claimed domains!",
        "today",
    ),
)


# --- Schemas ---------------------------------------------------------------------

class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    action_route: Optional[str] = None
    read: bool
    created_at: datetime


class NotificationsResponse(BaseModel):
    unread_count: int
    items: List[NotificationOut]


class SuggestedChallengeOut(BaseModel):
    id: int
    title: str
    description: str
    course_distance_m: float
    target_seconds: float
    win_xp: int
    participants: int
    joined: bool
    is_global: bool = True


class OsirianSuggestionOut(BaseModel):
    user_id: int
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    rank: str
    title: str
    identity: str
    xp: int
    streak_days: int
    domains_claimed: int
    verified_workouts: int
    followers_count: int
    following: bool
    trending_reason: str


class FollowStatusOut(BaseModel):
    user_id: int
    following: bool
    followers_count: int


class DismissOut(BaseModel):
    user_id: int
    dismissed: bool


class PostWorkoutSummary(BaseModel):
    exercise_key: Optional[str] = None
    exercise_name: Optional[str] = None
    sets: int = 1
    reps_per_set: int = 0
    total_reps: int = 0
    hold_s: float = 0.0
    distance_m: float = 0.0
    duration_s: float = 0.0
    domain_area_sqkm: float = 0.0
    streak_days: int = 0
    crystals_earned: int = 0
    xp_earned: int = 0
    measure_label: Optional[str] = None


class PostCommentOut(BaseModel):
    id: int
    post_id: int
    user_id: int
    author_name: str
    author_avatar_url: Optional[str] = None
    author_rank: str
    body: str
    created_at: datetime


class FeedPostOut(BaseModel):
    id: int
    user_id: int
    author_name: str
    author_handle: str
    author_avatar_url: Optional[str] = None
    author_rank: str
    author_title: str
    kind: str
    caption: str
    media_url: Optional[str] = None
    summary: PostWorkoutSummary
    reactions: Dict[str, int]
    total_reactions: int
    my_reaction: Optional[str] = None
    comment_count: int
    recent_comments: List[PostCommentOut] = Field(default_factory=list)
    share_count: int
    created_at: datetime


class FeedPostsResponse(BaseModel):
    items: List[FeedPostOut]


class PostCreateIn(BaseModel):
    kind: Literal["workout", "run", "domain_claim", "streak", "crystal_earn", "custom"] = "workout"
    caption: str = Field(default="", max_length=600)
    media_url: Optional[str] = Field(default=None, max_length=500)
    exercise_key: Optional[str] = Field(default=None, max_length=32)
    sets: int = Field(default=1, ge=1, le=50)
    reps_per_set: int = Field(default=0, ge=0, le=2000)
    total_reps: int = Field(default=0, ge=0, le=10000)
    hold_s: float = Field(default=0.0, ge=0.0, le=36000.0)
    distance_m: float = Field(default=0.0, ge=0.0, le=500000.0)
    duration_s: float = Field(default=0.0, ge=0.0, le=86400.0)
    domain_area_sqkm: float = Field(default=0.0, ge=0.0, le=10000.0)
    streak_days: int = Field(default=0, ge=0, le=10000)
    crystals_earned: int = Field(default=0, ge=0, le=100000)
    xp_earned: int = Field(default=0, ge=0, le=100000)
    related_run_id: Optional[int] = None
    related_exercise_session_id: Optional[int] = None
    related_domain_id: Optional[int] = None
    visibility: Literal["public", "followers"] = "public"


class PostReactionIn(BaseModel):
    reaction: Literal["fire", "like", "clap", "crown"]


class PostCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=400)


class PostShareOut(BaseModel):
    post_id: int
    share_count: int
    share_text: str
    share_url: str


# --- Helpers ---------------------------------------------------------------------

def create_notification(
    db: Session,
    user_id: int,
    kind: str,
    title: str,
    body: str,
    action_route: Optional[str] = None,
) -> models.PlayerNotification:
    row = models.PlayerNotification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        action_route=action_route,
    )
    db.add(row)
    return row


def _ensure_welcome_notifications(db: Session, user_id: int) -> None:
    existing = db.query(models.PlayerNotification.id).filter(
        models.PlayerNotification.user_id == user_id
    ).first()
    if existing is not None:
        return
    for kind, title, body, route in SYSTEM_WELCOME_NOTIFICATIONS:
        db.add(models.PlayerNotification(
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            action_route=route,
        ))
    db.flush()


def _avatar_for(profile: models.PlayerProfile) -> str:
    if profile.avatar_url:
        return profile.avatar_url
    return f"osiris://avatar/{profile.referral_code[:4].lower()}"


def _measure_label(summary: dict[str, Any]) -> str:
    ex_key = summary.get("exercise_key")
    ex_name = summary.get("exercise_name")
    sets = int(summary.get("sets") or 1)
    reps_per_set = int(summary.get("reps_per_set") or 0)
    total_reps = int(summary.get("total_reps") or 0)
    hold_s = float(summary.get("hold_s") or 0.0)
    dist_m = float(summary.get("distance_m") or 0.0)
    area = float(summary.get("domain_area_sqkm") or 0.0)
    if ex_key and ex_name:
        if hold_s > 0:
            per_set = int(round(hold_s / max(sets, 1)))
            return f"{ex_name} - {per_set}s x {sets}" if sets > 1 else f"{ex_name} - {int(round(hold_s))}s hold"
        if reps_per_set > 0 and sets > 1:
            return f"{ex_name} - {reps_per_set} x {sets} ({total_reps or reps_per_set * sets} reps)"
        if total_reps > 0:
            return f"{ex_name} - {total_reps} x 1" if sets == 1 else f"{ex_name} - {total_reps} reps"
    if area > 0:
        return f"Domain Claimed - {area:.3f} km²"
    if dist_m > 0:
        return f"GPS Workout - {dist_m / 1000.0:.2f} km"
    if summary.get("crystals_earned", 0) > 0:
        return f"+{int(summary['crystals_earned'])} Mana Crystals"
    if summary.get("streak_days", 0) > 0:
        return f"{int(summary['streak_days'])}-Day Streak"
    return "Osiris Activity"


# --- 1. Notifications ------------------------------------------------------------

@router.get("/api/v2/me/notifications", response_model=NotificationsResponse)
def list_my_notifications(
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    _ensure_welcome_notifications(db, uid)
    db.commit()
    rows = (
        db.query(models.PlayerNotification)
        .filter(models.PlayerNotification.user_id == uid)
        .order_by(models.PlayerNotification.created_at.desc(), models.PlayerNotification.id.desc())
        .limit(limit)
        .all()
    )
    unread = (
        db.query(func.count(models.PlayerNotification.id))
        .filter(models.PlayerNotification.user_id == uid, models.PlayerNotification.read_at.is_(None))
        .scalar()
        or 0
    )
    return NotificationsResponse(
        unread_count=int(unread),
        items=[
            NotificationOut(
                id=r.id,
                kind=r.kind,
                title=r.title,
                body=r.body,
                action_route=r.action_route,
                read=r.read_at is not None,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.post("/api/v2/me/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    row = (
        db.query(models.PlayerNotification)
        .filter(models.PlayerNotification.id == notification_id, models.PlayerNotification.user_id == uid)
        .first()
    )
    if row is None:
        raise _api_error(404, "NOTIFICATION_NOT_FOUND", "Notification not found")
    if row.read_at is None:
        row.read_at = _now_naive_utc()
        db.commit()
        db.refresh(row)
    return NotificationOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        action_route=row.action_route,
        read=True,
        created_at=row.created_at,
    )


@router.post("/api/v2/me/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    now = _now_naive_utc()
    updated = (
        db.query(models.PlayerNotification)
        .filter(models.PlayerNotification.user_id == uid, models.PlayerNotification.read_at.is_(None))
        .update({models.PlayerNotification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return {"marked_read": int(updated)}


# --- 2. Suggested Global Challenges (Circular-Floating Card Deck) ----------------

@router.get("/api/v2/challenges/suggested", response_model=List[SuggestedChallengeOut])
def suggested_global_challenges(
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Returns global challenges that any player can join from anywhere, formatted for the
    Home screen's circular-floating card deck with a 1-line description and join state."""
    uid = token_data["id"]
    now = _now_naive_utc()
    blocked = player_safety.blocked_user_ids(db, uid)
    rows = (
        db.query(models.Challenge, models.Course)
        .join(models.Course, models.Course.id == models.Challenge.course_id)
        .filter(
            models.Challenge.status == "open",
            models.Challenge.closes_at > now,
            models.Course.status == "active",
            models.Challenge.creator_id.notin_(blocked or {-1}),
        )
        .order_by(models.Challenge.closes_at.asc(), models.Challenge.id.desc())
        .limit(limit)
        .all()
    )
    changed = any([_refresh_challenge_status(db, ch, now) for ch, _ in rows])
    open_rows = [(ch, course) for ch, course in rows if ch.status == "open"]
    ids = [ch.id for ch, _ in open_rows]
    stats = ChallengeStats.load(db, ids, uid)
    counts = {
        cid: int(n)
        for cid, n in db.query(models.ChallengeAttempt.challenge_id, func.count(models.ChallengeAttempt.id))
        .filter(models.ChallengeAttempt.challenge_id.in_(ids or [-1]))
        .group_by(models.ChallengeAttempt.challenge_id)
        .all()
    }
    if changed:
        db.commit()

    out: List[SuggestedChallengeOut] = []
    for ch, course in open_rows:
        km = round(course.distance_m / 1000.0, 1)
        mins = max(1, int(round(ch.target_seconds / 60.0)))
        desc = (
            ch.safety_notes.strip()
            if ch.safety_notes and ch.safety_notes.strip()
            else f"Global {km} km challenge · Beat {mins} min anywhere for +{ch.win_xp} XP"
        )
        # Keep 1-line concise
        if len(desc) > 96:
            desc = desc[:93].rstrip() + "..."
        out.append(
            SuggestedChallengeOut(
                id=ch.id,
                title=ch.title,
                description=desc,
                course_distance_m=round(course.distance_m, 1),
                target_seconds=round(ch.target_seconds, 1),
                win_xp=ch.win_xp,
                participants=counts.get(ch.id, 0),
                joined=ch.id in stats.my_attempts,
                is_global=True,
            )
        )
    return out


# --- 3. Suggested Osirians & Trending ("See All") --------------------------------

def _build_osirian_cards(
    db: Session,
    viewer_id: int,
    candidate_ids: List[int],
    followed_ids: set[int],
) -> List[OsirianSuggestionOut]:
    if not candidate_ids:
        return []
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(candidate_ids)).all()}
    profiles = {
        p.user_id: p
        for p in db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(candidate_ids)).all()
    }
    run_counts = {
        uid: int(n)
        for uid, n in db.query(models.RunSession.user_id, func.count(models.RunSession.id))
        .filter(models.RunSession.user_id.in_(candidate_ids), models.RunSession.verification_status == "accepted")
        .group_by(models.RunSession.user_id)
        .all()
    }
    ex_counts = {
        uid: int(n)
        for uid, n in db.query(models.ExerciseSession.user_id, func.count(models.ExerciseSession.id))
        .filter(models.ExerciseSession.user_id.in_(candidate_ids), models.ExerciseSession.status == "verified")
        .group_by(models.ExerciseSession.user_id)
        .all()
    }
    domain_counts = {
        uid: int(n)
        for uid, n in db.query(models.Domain.owner_id, func.count(models.Domain.id))
        .filter(models.Domain.owner_id.in_(candidate_ids))
        .group_by(models.Domain.owner_id)
        .all()
    }
    follower_counts = {
        uid: int(n)
        for uid, n in db.query(models.UserFollow.followed_id, func.count(models.UserFollow.id))
        .filter(models.UserFollow.followed_id.in_(candidate_ids))
        .group_by(models.UserFollow.followed_id)
        .all()
    }

    cards: List[OsirianSuggestionOut] = []
    for uid in candidate_ids:
        u = users.get(uid)
        if u is None or u.suspended_at is not None:
            continue
        p = profiles.get(uid) or get_or_create_profile(db, u)
        workouts = run_counts.get(uid, 0) + ex_counts.get(uid, 0)
        domains = domain_counts.get(uid, 0)
        followers = follower_counts.get(uid, 0)
        xp = int(u.xp or 0)
        streak = int(u.streak or 0)
        if workouts > 0:
            reason = f"{workouts} verified workouts · {xp} XP"
        elif domains > 0:
            reason = f"{domains} domains claimed · {u.title or 'Awakened'}"
        elif streak > 0:
            reason = f"{streak}-day workout streak"
        else:
            reason = f"{challenge_rules.performance_rank(xp)} · {quest_rules.identity_for(p.goal)}"
        cards.append(
            OsirianSuggestionOut(
                user_id=uid,
                handle=p.referral_code,
                display_name=p.display_name,
                avatar_url=_avatar_for(p),
                rank=challenge_rules.performance_rank(xp),
                title=u.title or "Unawakened",
                identity=quest_rules.identity_for(p.goal),
                xp=xp,
                streak_days=streak,
                domains_claimed=domains,
                verified_workouts=workouts,
                followers_count=followers,
                following=uid in followed_ids,
                trending_reason=reason,
            )
        )
    cards.sort(
        key=lambda c: (
            -(c.verified_workouts * 25 + c.domains_claimed * 40 + c.followers_count * 15 + c.xp),
            -c.user_id,
        )
    )
    return cards


@router.get("/api/v2/osirians/suggested", response_model=List[OsirianSuggestionOut])
def suggested_osirians(
    limit: int = Query(15, ge=1, le=100),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Instagram-style suggested Osirians carousel. Excludes the viewer, blocked users,
    already-followed users, and anyone the viewer dismissed via the top-right 'x' button."""
    uid = token_data["id"]
    blocked = player_safety.blocked_user_ids(db, uid)
    followed = {
        fid
        for (fid,) in db.query(models.UserFollow.followed_id)
        .filter(models.UserFollow.follower_id == uid)
        .all()
    }
    dismissed = {
        did
        for (did,) in db.query(models.DismissedSuggestion.dismissed_user_id)
        .filter(models.DismissedSuggestion.user_id == uid)
        .all()
    }
    excluded = {uid} | blocked | followed | dismissed
    candidate_ids = [
        cid
        for (cid,) in db.query(models.User.id)
        .filter(models.User.suspended_at.is_(None), models.User.id.notin_(excluded))
        .order_by(models.User.xp.desc(), models.User.id.desc())
        .limit(max(limit * 4, 200))
        .all()
    ]
    cards = _build_osirian_cards(db, uid, candidate_ids, followed)
    db.commit()
    return cards[:limit]


@router.get("/api/v2/osirians/trending", response_model=List[OsirianSuggestionOut])
def trending_osirians(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Backs the 'See All' option next to Suggested Osirians: shows influential and trending
    Osirians ranked by their verified workouts, domains, followers, and XP."""
    uid = token_data["id"]
    blocked = player_safety.blocked_user_ids(db, uid)
    followed = {
        fid
        for (fid,) in db.query(models.UserFollow.followed_id)
        .filter(models.UserFollow.follower_id == uid)
        .all()
    }
    excluded = {uid} | blocked
    candidate_ids = [
        cid
        for (cid,) in db.query(models.User.id)
        .filter(models.User.suspended_at.is_(None), models.User.id.notin_(excluded))
        .order_by(models.User.xp.desc(), models.User.id.desc())
        .limit(limit * 2)
        .all()
    ]
    cards = _build_osirian_cards(db, uid, candidate_ids, followed)
    db.commit()
    return cards[:limit]


@router.post("/api/v2/osirians/{target_user_id}/follow", response_model=FollowStatusOut)
def follow_osirian(
    target_user_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    if target_user_id == uid:
        raise _api_error(422, "SELF_FOLLOW", "You cannot follow yourself")
    target = db.query(models.User).filter(models.User.id == target_user_id, models.User.suspended_at.is_(None)).first()
    if target is None or player_safety.is_blocked_between(db, uid, target_user_id):
        raise _api_error(404, "PLAYER_NOT_FOUND", "Osirian not found")
    existing = (
        db.query(models.UserFollow)
        .filter(models.UserFollow.follower_id == uid, models.UserFollow.followed_id == target_user_id)
        .first()
    )
    if existing is None:
        db.add(models.UserFollow(follower_id=uid, followed_id=target_user_id))
        follower_user = db.query(models.User).filter(models.User.id == uid).first()
        follower_profile = get_or_create_profile(db, follower_user)
        create_notification(
            db,
            user_id=target_user_id,
            kind="social_follow",
            title="New Osirian Follower",
            body=f"{follower_profile.display_name} started following your workouts.",
            action_route="today",
        )
        db.commit()
    count = (
        db.query(func.count(models.UserFollow.id))
        .filter(models.UserFollow.followed_id == target_user_id)
        .scalar()
        or 0
    )
    return FollowStatusOut(user_id=target_user_id, following=True, followers_count=int(count))


@router.delete("/api/v2/osirians/{target_user_id}/follow", response_model=FollowStatusOut)
def unfollow_osirian(
    target_user_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    db.query(models.UserFollow).filter(
        models.UserFollow.follower_id == uid, models.UserFollow.followed_id == target_user_id
    ).delete(synchronize_session=False)
    db.commit()
    count = (
        db.query(func.count(models.UserFollow.id))
        .filter(models.UserFollow.followed_id == target_user_id)
        .scalar()
        or 0
    )
    return FollowStatusOut(user_id=target_user_id, following=False, followers_count=int(count))


@router.post("/api/v2/osirians/{target_user_id}/dismiss", response_model=DismissOut)
def dismiss_osirian_suggestion(
    target_user_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Permanently removes `target_user_id` from the caller's Suggested Osirians carousel."""
    uid = token_data["id"]
    if target_user_id == uid:
        raise _api_error(422, "SELF_DISMISS", "Cannot dismiss yourself")
    existing = (
        db.query(models.DismissedSuggestion)
        .filter(
            models.DismissedSuggestion.user_id == uid,
            models.DismissedSuggestion.dismissed_user_id == target_user_id,
        )
        .first()
    )
    if existing is None:
        db.add(models.DismissedSuggestion(user_id=uid, dismissed_user_id=target_user_id))
        db.commit()
    return DismissOut(user_id=target_user_id, dismissed=True)


# --- 4. People's Posts (Workouts, Domains, Streaks, Crystals, React, Comment, Share) ---

def _hydrate_posts(db: Session, posts: List[models.SocialPost], viewer_id: int) -> List[FeedPostOut]:
    if not posts:
        return []
    post_ids = [p.id for p in posts]
    author_ids = {p.user_id for p in posts}

    comments_by_post: dict[int, list[models.PostComment]] = {pid: [] for pid in post_ids}
    all_comments = (
        db.query(models.PostComment)
        .filter(models.PostComment.post_id.in_(post_ids))
        .order_by(models.PostComment.created_at.asc(), models.PostComment.id.asc())
        .all()
    )
    for c in all_comments:
        comments_by_post[c.post_id].append(c)
        author_ids.add(c.user_id)

    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(author_ids or {-1})).all()}
    profiles = {
        p.user_id: p
        for p in db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(author_ids or {-1})).all()
    }
    for uid, u in users.items():
        if uid not in profiles:
            profiles[uid] = get_or_create_profile(db, u)

    reactions_by_post: dict[int, dict[str, int]] = {pid: {} for pid in post_ids}
    my_reactions: dict[int, str] = {}
    for r in db.query(models.PostReaction).filter(models.PostReaction.post_id.in_(post_ids)).all():
        bucket = reactions_by_post[r.post_id]
        bucket[r.reaction] = bucket.get(r.reaction, 0) + 1
        if r.user_id == viewer_id:
            my_reactions[r.post_id] = r.reaction

    out: List[FeedPostOut] = []
    for p in posts:
        u = users.get(p.user_id)
        prof = profiles.get(p.user_id)
        if u is None or prof is None:
            continue
        raw_summary = json.loads(p.workout_summary_json or "{}")
        raw_summary["measure_label"] = _measure_label(raw_summary)
        summary = PostWorkoutSummary(**{k: v for k, v in raw_summary.items() if k in PostWorkoutSummary.model_fields})

        post_comments = comments_by_post.get(p.id, [])
        recent_comments_out = []
        for c in post_comments[-3:]:
            cu = users.get(c.user_id)
            cp = profiles.get(c.user_id)
            if cu and cp:
                recent_comments_out.append(
                    PostCommentOut(
                        id=c.id,
                        post_id=c.post_id,
                        user_id=c.user_id,
                        author_name=cp.display_name,
                        author_avatar_url=_avatar_for(cp),
                        author_rank=challenge_rules.performance_rank(cu.xp or 0),
                        body=c.body,
                        created_at=c.created_at,
                    )
                )

        rx = reactions_by_post.get(p.id, {})
        out.append(
            FeedPostOut(
                id=p.id,
                user_id=p.user_id,
                author_name=prof.display_name,
                author_handle=prof.referral_code,
                author_avatar_url=_avatar_for(prof),
                author_rank=challenge_rules.performance_rank(u.xp or 0),
                author_title=u.title or "Unawakened",
                kind=p.kind,
                caption=p.caption,
                media_url=p.media_url,
                summary=summary,
                reactions=rx,
                total_reactions=sum(rx.values()),
                my_reaction=my_reactions.get(p.id),
                comment_count=len(post_comments),
                recent_comments=recent_comments_out,
                share_count=p.share_count or 0,
                created_at=p.created_at,
            )
        )
    return out


@router.get("/api/v2/feed/posts", response_model=FeedPostsResponse)
def list_feed_posts(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    blocked = player_safety.blocked_user_ids(db, uid)
    followed = {
        fid
        for (fid,) in db.query(models.UserFollow.followed_id)
        .filter(models.UserFollow.follower_id == uid)
        .all()
    }
    posts = (
        db.query(models.SocialPost)
        .filter(
            models.SocialPost.user_id.notin_(blocked or {-1}),
            (models.SocialPost.visibility == "public")
            | (models.SocialPost.user_id == uid)
            | (models.SocialPost.user_id.in_(followed or {-1})),
        )
        .order_by(models.SocialPost.created_at.desc(), models.SocialPost.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = _hydrate_posts(db, posts, uid)
    db.commit()
    return FeedPostsResponse(items=items)


@router.post("/api/v2/feed/posts", response_model=FeedPostOut, status_code=201)
def create_feed_post(
    req: PostCreateIn,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    user = db.query(models.User).filter(models.User.id == uid).first()
    ex_name = None
    if req.exercise_key:
        if req.exercise_key in exercise_rules.BY_KEY:
            ex_name = exercise_rules.BY_KEY[req.exercise_key]["name"]
        else:
            ex_name = req.exercise_key.replace("_", " ").title()

    total_reps = req.total_reps or (req.reps_per_set * req.sets)
    summary_dict: dict[str, Any] = {
        "exercise_key": req.exercise_key,
        "exercise_name": ex_name,
        "sets": req.sets,
        "reps_per_set": req.reps_per_set,
        "total_reps": total_reps,
        "hold_s": round(req.hold_s, 1),
        "distance_m": round(req.distance_m, 1),
        "duration_s": round(req.duration_s, 1),
        "domain_area_sqkm": round(req.domain_area_sqkm, 4),
        "streak_days": req.streak_days or int(user.streak or 0),
        "crystals_earned": req.crystals_earned,
        "xp_earned": req.xp_earned,
    }
    summary_dict["measure_label"] = _measure_label(summary_dict)

    caption = req.caption.strip()
    if not caption:
        caption = f"Completed {summary_dict['measure_label']} on Osiris!"

    post = models.SocialPost(
        user_id=uid,
        kind=req.kind,
        caption=caption,
        media_url=req.media_url,
        workout_summary_json=json.dumps(summary_dict, sort_keys=True),
        related_run_id=req.related_run_id,
        related_exercise_session_id=req.related_exercise_session_id,
        related_domain_id=req.related_domain_id,
        visibility=req.visibility,
        share_count=0,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _hydrate_posts(db, [post], uid)[0]


@router.post("/api/v2/feed/posts/{post_id}/react", response_model=FeedPostOut)
def react_to_post(
    post_id: int,
    req: PostReactionIn,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    post = db.query(models.SocialPost).filter(models.SocialPost.id == post_id).first()
    if post is None or player_safety.is_blocked_between(db, uid, post.user_id):
        raise _api_error(404, "POST_NOT_FOUND", "Post not found")

    existing = (
        db.query(models.PostReaction)
        .filter(models.PostReaction.post_id == post_id, models.PostReaction.user_id == uid)
        .first()
    )
    if existing is not None:
        if existing.reaction == req.reaction:
            db.delete(existing)
        else:
            existing.reaction = req.reaction
    else:
        db.add(models.PostReaction(post_id=post_id, user_id=uid, reaction=req.reaction))
        if post.user_id != uid:
            actor_user = db.query(models.User).filter(models.User.id == uid).first()
            actor_profile = get_or_create_profile(db, actor_user)
            create_notification(
                db,
                user_id=post.user_id,
                kind="post_reaction",
                title="New Reaction on Your Post",
                body=f"{actor_profile.display_name} reacted ({req.reaction}) to your workout post.",
                action_route="today",
            )
    db.commit()
    db.refresh(post)
    return _hydrate_posts(db, [post], uid)[0]


@router.get("/api/v2/feed/posts/{post_id}/comments", response_model=List[PostCommentOut])
def list_post_comments(
    post_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    post = db.query(models.SocialPost).filter(models.SocialPost.id == post_id).first()
    if post is None or player_safety.is_blocked_between(db, uid, post.user_id):
        raise _api_error(404, "POST_NOT_FOUND", "Post not found")
    rows = (
        db.query(models.PostComment)
        .filter(models.PostComment.post_id == post_id)
        .order_by(models.PostComment.created_at.asc(), models.PostComment.id.asc())
        .limit(limit)
        .all()
    )
    user_ids = {r.user_id for r in rows} or {-1}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()}
    profiles = {
        p.user_id: p for p in db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(user_ids)).all()
    }
    out: List[PostCommentOut] = []
    for r in rows:
        u = users.get(r.user_id)
        if u is None:
            continue
        p = profiles.get(r.user_id) or get_or_create_profile(db, u)
        out.append(
            PostCommentOut(
                id=r.id,
                post_id=r.post_id,
                user_id=r.user_id,
                author_name=p.display_name,
                author_avatar_url=_avatar_for(p),
                author_rank=challenge_rules.performance_rank(u.xp or 0),
                body=r.body,
                created_at=r.created_at,
            )
        )
    db.commit()
    return out


@router.post("/api/v2/feed/posts/{post_id}/comments", response_model=PostCommentOut, status_code=201)
def add_post_comment(
    post_id: int,
    req: PostCommentIn,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    post = db.query(models.SocialPost).filter(models.SocialPost.id == post_id).first()
    if post is None or player_safety.is_blocked_between(db, uid, post.user_id):
        raise _api_error(404, "POST_NOT_FOUND", "Post not found")
    body = req.body.strip()
    if not body:
        raise _api_error(422, "EMPTY_COMMENT", "Comment cannot be empty")
    comment = models.PostComment(post_id=post_id, user_id=uid, body=body)
    db.add(comment)
    user = db.query(models.User).filter(models.User.id == uid).first()
    profile = get_or_create_profile(db, user)
    if post.user_id != uid:
        create_notification(
            db,
            user_id=post.user_id,
            kind="post_comment",
            title="New Comment on Your Post",
            body=f"{profile.display_name}: {body[:80]}",
            action_route="today",
        )
    db.commit()
    db.refresh(comment)
    return PostCommentOut(
        id=comment.id,
        post_id=comment.post_id,
        user_id=uid,
        author_name=profile.display_name,
        author_avatar_url=_avatar_for(profile),
        author_rank=challenge_rules.performance_rank(user.xp or 0),
        body=comment.body,
        created_at=comment.created_at,
    )


@router.post("/api/v2/feed/posts/{post_id}/share", response_model=PostShareOut)
def share_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    post = db.query(models.SocialPost).filter(models.SocialPost.id == post_id).first()
    if post is None or player_safety.is_blocked_between(db, uid, post.user_id):
        raise _api_error(404, "POST_NOT_FOUND", "Post not found")
    post.share_count = (post.share_count or 0) + 1
    author = db.query(models.User).filter(models.User.id == post.user_id).first()
    author_profile = get_or_create_profile(db, author)
    summary = json.loads(post.workout_summary_json or "{}")
    label = _measure_label(summary)
    base = settings.public_base_url() or (str(request.base_url).rstrip("/") if settings.is_dev_env() else "https://api.osiris.fit")
    url = f"{base}/p/{author_profile.referral_code}"
    text = f"{author_profile.display_name} on Osiris: {post.caption} ({label}) — {url}"
    db.commit()
    return PostShareOut(post_id=post.id, share_count=post.share_count, share_text=text, share_url=url)
