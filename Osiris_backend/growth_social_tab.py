# ruff: noqa: B008
"""The Social tab: an Instagram-style home for people you follow.

Endpoints:
  - GET    /api/v2/social/feed                                   following feed + who trained today
  - GET    /api/v2/social/discover                               "for you" posts from people you don't follow
  - GET    /api/v2/social/search                                 people by name or handle
  - GET    /api/v2/social/users/{user_id}                        a player's profile and posts
  - POST   /api/v2/social/posts                                  photo, workout stats, chart, or all together
  - DELETE /api/v2/social/posts/{post_id}                        delete your own post
  - GET    /api/v2/social/media/{token}                          a post's photo
  - GET    /api/v2/social/conversations                          direct-message inbox
  - GET    /api/v2/social/conversations/{user_id}/messages       one thread
  - POST   /api/v2/social/conversations/{user_id}/messages       send a message
  - POST   /api/v2/social/conversations/{user_id}/read           mark a thread read

Workout stats on a post are copied from the server's own training sessions; the client only names
them. Direct messages are for connections (either player follows the other) and never cross a block.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import secrets
from datetime import date, datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from core.clock import _now_naive_utc
from core.errors import _api_error
from core.rate_limit import _rl_social
from core.security import get_active_player
from database import get_db
from growth_api import get_or_create_profile
from growth_feed import (
    FeedPostOut,
    _avatar_for,
    _hydrate_posts,
    _measure_label,
    can_view_post,
    create_notification,
)
from services import challenges as challenge_rules
from services import player_safety
from services import training

router = APIRouter()

MAX_PHOTO_BYTES = 300 * 1024
MAX_ATTACHMENTS = 4
CHART_WEEKS = 8
DISCOVER_WINDOW = timedelta(days=30)
DISCOVER_CANDIDATES = 300
ACTIVE_WINDOW = timedelta(hours=24)
INBOX_SCAN = 1000


# --- Schemas ---------------------------------------------------------------------


class SocialUserOut(BaseModel):
    user_id: int
    display_name: str
    handle: str
    avatar_url: Optional[str] = None
    rank: str
    following: bool
    follows_me: bool


class ActiveFriendOut(BaseModel):
    """A followed player who trained in the last 24 hours (the stories row)."""

    user_id: int
    display_name: str
    avatar_url: Optional[str] = None
    activity_key: str
    activity_name: str
    minutes: int


class SocialFeedOut(BaseModel):
    active_today: List[ActiveFriendOut]
    items: List[FeedPostOut]
    next_before_id: Optional[int] = None


class DiscoverOut(BaseModel):
    interests: List[str]
    items: List[FeedPostOut]


class SocialProfileOut(BaseModel):
    user: SocialUserOut
    bio: Optional[str] = None
    title: str
    posts_count: int
    followers_count: int
    following_count: int
    streak_days: int
    week_minutes: int
    week_sessions: int
    is_me: bool
    can_message: bool
    posts: List[FeedPostOut]


class SocialPostIn(BaseModel):
    caption: str = Field(default="", max_length=600)
    photo_jpeg_base64: Optional[str] = Field(default=None, max_length=500_000)  # 300 KB of JPEG
    training_session_ids: List[int] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)
    chart: Literal["none", "weekly_progress"] = "none"
    visibility: Literal["public", "followers"] = "public"


class DirectMessageOut(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    body: str
    created_at: datetime
    read: bool
    mine: bool


class ConversationOut(BaseModel):
    user: SocialUserOut
    last_message: DirectMessageOut
    unread_count: int


class InboxOut(BaseModel):
    unread_total: int
    items: List[ConversationOut]


class ThreadOut(BaseModel):
    user: SocialUserOut
    can_message: bool
    items: List[DirectMessageOut]


class DirectMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


# --- Helpers ---------------------------------------------------------------------


def _followed_ids(db: Session, uid: int) -> set[int]:
    return {f for (f,) in db.query(models.UserFollow.followed_id).filter(models.UserFollow.follower_id == uid)}


def _follower_ids(db: Session, uid: int) -> set[int]:
    return {f for (f,) in db.query(models.UserFollow.follower_id).filter(models.UserFollow.followed_id == uid)}


def _user_cards(db: Session, viewer_id: int, ids: list[int]) -> dict[int, SocialUserOut]:
    if not ids:
        return {}
    users = {u.id: u for u in db.query(models.User).filter(models.User.id.in_(ids))}
    profiles = {p.user_id: p for p in db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(ids))}
    following = _followed_ids(db, viewer_id)
    followers = _follower_ids(db, viewer_id)
    out: dict[int, SocialUserOut] = {}
    for uid in ids:
        u = users.get(uid)
        if u is None:
            continue
        p = profiles.get(uid) or get_or_create_profile(db, u)
        out[uid] = SocialUserOut(
            user_id=uid,
            display_name=p.display_name,
            handle=p.referral_code,
            avatar_url=_avatar_for(p),
            rank=challenge_rules.performance_rank(u.xp or 0),
            following=uid in following,
            follows_me=uid in followers,
        )
    return out


def _visible_player(db: Session, viewer_id: int, user_id: int) -> models.User:
    """A player the viewer may see: exists, not suspended (unless it is the viewer), no block between."""
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u is None or (
        user_id != viewer_id
        and (u.suspended_at is not None or player_safety.is_blocked_between(db, viewer_id, user_id))
    ):
        raise _api_error(404, "PLAYER_NOT_FOUND", "Osirian not found")
    return u


def _pair_key(a: int, b: int) -> str:
    low, high = sorted((a, b))
    return f"{low}:{high}"


def _can_message(db: Session, uid: int, other: int) -> bool:
    return other != uid and other in training.connection_ids(db, uid)


def _message_out(m: models.DirectMessage, viewer_id: int) -> DirectMessageOut:
    return DirectMessageOut(
        id=m.id,
        sender_id=m.sender_id,
        recipient_id=m.recipient_id,
        body=m.body,
        created_at=m.created_at,
        read=m.read_at is not None,
        mine=m.sender_id == viewer_id,
    )


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weekly_chart(db: Session, uid: int, today: date) -> dict:
    starts = [_monday(today) - timedelta(weeks=n) for n in reversed(range(CHART_WEEKS))]
    minutes = {s: 0.0 for s in starts}
    for local_date, duration in db.query(models.TrainingSession.local_date, models.TrainingSession.duration_s).filter(
        models.TrainingSession.user_id == uid, models.TrainingSession.local_date >= starts[0].isoformat()
    ):
        week = _monday(date.fromisoformat(local_date))
        if week in minutes:
            minutes[week] += duration / 60
    return {
        "kind": "weekly_progress",
        "title": f"Training minutes, last {CHART_WEEKS} weeks",
        "unit": "min",
        "labels": [s.strftime("%d %b") for s in starts],
        "values": [round(minutes[s], 1) for s in starts],
    }


def _is_pr(db: Session, row: models.TrainingSession) -> bool:
    metric = training.BY_KEY[row.activity_key]["metric"]
    value = training.metric_value(row, metric)
    if value <= 0:
        return False
    others = (
        db.query(models.TrainingSession)
        .filter(
            models.TrainingSession.user_id == row.user_id,
            models.TrainingSession.activity_key == row.activity_key,
            models.TrainingSession.id != row.id,
        )
        .all()
    )
    return all(training.metric_value(o, metric) < value for o in others)


def _attachment(db: Session, row: models.TrainingSession) -> dict:
    activity = training.BY_KEY.get(row.activity_key, {"name": row.activity_key.title(), "kind": "sensor"})
    return {
        "session_id": row.id,
        "activity_key": row.activity_key,
        "activity_name": activity["name"],
        "activity_kind": activity["kind"],
        "started_at": row.started_at.isoformat(),
        "duration_s": round(row.duration_s, 1),
        "distance_m": round(row.distance_m, 1),
        "elevation_gain_m": round(row.elevation_gain_m, 1),
        "reps": row.reps,
        "hr_avg": row.hr_avg,
        "speed_avg": row.speed_avg,
        "is_pr": activity.get("metric") is not None and _is_pr(db, row),
    }


def _post_activity_keys(post: models.SocialPost) -> set[str]:
    keys = {a.get("activity_key") for a in json.loads(post.attachments_json or "[]")}
    key = json.loads(post.workout_summary_json or "{}").get("exercise_key")
    if key:
        keys.add(key)
    keys.discard(None)
    return {str(k) for k in keys}


# --- Feed, discover, search, profile ----------------------------------------------


@router.get("/api/v2/social/feed", response_model=SocialFeedOut)
def social_feed(
    limit: int = Query(20, ge=1, le=50),
    before_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Posts by people the player follows, and their own, newest first. Page with `before_id`."""
    uid = token_data["id"]
    blocked = player_safety.blocked_user_ids(db, uid)
    followed = _followed_ids(db, uid) - blocked
    q = db.query(models.SocialPost).filter(models.SocialPost.user_id.in_(followed | {uid}))
    if before_id is not None:
        q = q.filter(models.SocialPost.id < before_id)
    posts = q.order_by(models.SocialPost.id.desc()).limit(limit + 1).all()
    page = posts[:limit]

    active: List[ActiveFriendOut] = []
    if before_id is None and followed:
        since = _now_naive_utc() - ACTIVE_WINDOW
        latest: dict[int, models.TrainingSession] = {}
        for row in (
            db.query(models.TrainingSession)
            .filter(models.TrainingSession.user_id.in_(followed), models.TrainingSession.started_at >= since)
            .order_by(models.TrainingSession.started_at.desc())
        ):
            latest.setdefault(row.user_id, row)
        suspended = {
            i
            for (i,) in db.query(models.User.id).filter(
                models.User.id.in_(list(latest)), models.User.suspended_at.isnot(None)
            )
        }
        cards = _user_cards(db, uid, [i for i in latest if i not in suspended])
        for friend_id, row in latest.items():
            card = cards.get(friend_id)
            if card is None:
                continue
            activity = training.BY_KEY.get(row.activity_key, {"name": row.activity_key.title()})
            active.append(
                ActiveFriendOut(
                    user_id=friend_id,
                    display_name=card.display_name,
                    avatar_url=card.avatar_url,
                    activity_key=row.activity_key,
                    activity_name=activity["name"],
                    minutes=max(1, round(row.duration_s / 60)),
                )
            )
    items = _hydrate_posts(db, page, uid)
    db.commit()
    return SocialFeedOut(
        active_today=active,
        items=items,
        next_before_id=page[-1].id if len(posts) > limit and page else None,
    )


@router.get("/api/v2/social/discover", response_model=DiscoverOut)
def social_discover(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=500),
    activity: Optional[str] = Query(None, max_length=32),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Public posts from players the viewer does not follow, ranked by the viewer's interests (the
    activities they train), engagement and recency. `activity` narrows to one activity."""
    uid = token_data["id"]
    now = _now_naive_utc()
    excluded = {uid} | _followed_ids(db, uid) | player_safety.blocked_user_ids(db, uid)
    suspended = {i for (i,) in db.query(models.User.id).filter(models.User.suspended_at.isnot(None))}
    interests = [
        k
        for (k, _n) in db.query(models.TrainingSession.activity_key, func.count(models.TrainingSession.id))
        .filter(models.TrainingSession.user_id == uid)
        .group_by(models.TrainingSession.activity_key)
        .order_by(func.count(models.TrainingSession.id).desc())
        .limit(6)
    ]
    candidates = (
        db.query(models.SocialPost)
        .filter(
            models.SocialPost.visibility == "public",
            models.SocialPost.user_id.notin_((excluded | suspended) or {-1}),
            models.SocialPost.created_at >= now - DISCOVER_WINDOW,
        )
        .order_by(models.SocialPost.id.desc())
        .limit(DISCOVER_CANDIDATES)
        .all()
    )
    if activity:
        candidates = [p for p in candidates if activity in _post_activity_keys(p)]
    ids = [p.id for p in candidates] or [-1]
    reactions: dict[int, int] = {
        pid: int(n)
        for pid, n in db.query(models.PostReaction.post_id, func.count(models.PostReaction.id))
        .filter(models.PostReaction.post_id.in_(ids))
        .group_by(models.PostReaction.post_id)
        .all()
    }
    comments: dict[int, int] = {
        pid: int(n)
        for pid, n in db.query(models.PostComment.post_id, func.count(models.PostComment.id))
        .filter(models.PostComment.post_id.in_(ids))
        .group_by(models.PostComment.post_id)
        .all()
    }
    wanted = set(interests)

    def score(p: models.SocialPost) -> tuple[float, int]:
        overlap = len(_post_activity_keys(p) & wanted)
        engagement = reactions.get(p.id, 0) + 2 * comments.get(p.id, 0)
        age_days = (now - p.created_at).total_seconds() / 86_400
        has_stats = 0.5 if (p.chart_json or p.attachments_json not in (None, "", "[]")) else 0.0
        return 3.0 * overlap + math.log1p(engagement) + has_stats - 0.15 * age_days, p.id

    ranked = sorted(candidates, key=score, reverse=True)[offset : offset + limit]
    items = _hydrate_posts(db, ranked, uid)
    db.commit()
    return DiscoverOut(interests=interests, items=items)


@router.get("/api/v2/social/search", response_model=List[SocialUserOut])
def social_search(
    q: str = Query(..., min_length=2, max_length=40),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Players whose display name or handle contains `q`, ignoring case. Handle prefix matches first."""
    uid = token_data["id"]
    term = q.strip().lower()
    if len(term) < 2:
        raise HTTPException(status_code=422, detail="Type at least 2 characters")
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    excluded = {uid} | player_safety.blocked_user_ids(db, uid)
    rows = (
        db.query(models.PlayerProfile.user_id, models.PlayerProfile.display_name, models.PlayerProfile.referral_code)
        .join(models.User, models.User.id == models.PlayerProfile.user_id)
        .filter(
            models.User.suspended_at.is_(None),
            models.PlayerProfile.user_id.notin_(excluded),
            func.lower(models.PlayerProfile.display_name).like(pattern, escape="\\")
            | func.lower(models.PlayerProfile.referral_code).like(pattern, escape="\\"),
        )
        .limit(200)
        .all()
    )

    matches: list[tuple[int, str, str]] = [(int(r[0]), str(r[1]), str(r[2])) for r in rows]

    def rank(row: tuple[int, str, str]) -> tuple[int, int, str]:
        name, handle = row[1].lower(), row[2].lower()
        exact = 0 if term in (name, handle) else 1
        prefix = 0 if name.startswith(term) or handle.startswith(term) else 1
        return exact, prefix, name

    ordered = [r[0] for r in sorted(matches, key=rank)[:limit]]
    cards = _user_cards(db, uid, ordered)
    db.commit()
    return [cards[i] for i in ordered if i in cards]


@router.get("/api/v2/social/users/{user_id}", response_model=SocialProfileOut)
def social_profile(
    user_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    u = _visible_player(db, uid, user_id)
    profile = get_or_create_profile(db, u)
    card = _user_cards(db, uid, [user_id])[user_id]
    posts = [
        p
        for p in db.query(models.SocialPost)
        .filter(models.SocialPost.user_id == user_id)
        .order_by(models.SocialPost.id.desc())
        .limit(60)
        .all()
        if can_view_post(db, uid, p)
    ]
    week_start = _monday(date.today()).isoformat()
    week = (
        db.query(func.count(models.TrainingSession.id), func.coalesce(func.sum(models.TrainingSession.duration_s), 0.0))
        .filter(models.TrainingSession.user_id == user_id, models.TrainingSession.local_date >= week_start)
        .one()
    )
    out = SocialProfileOut(
        user=card,
        bio=profile.bio,
        title=u.title or "Unawakened",
        posts_count=len(posts),
        followers_count=len(_follower_ids(db, user_id)),
        following_count=len(_followed_ids(db, user_id)),
        streak_days=int(u.streak or 0),
        week_minutes=round(float(week[1]) / 60),
        week_sessions=int(week[0]),
        is_me=user_id == uid,
        can_message=_can_message(db, uid, user_id),
        posts=_hydrate_posts(db, posts[:30], uid),
    )
    db.commit()
    return out


# --- Posting -----------------------------------------------------------------------


@router.post("/api/v2/social/posts", response_model=FeedPostOut, status_code=201, dependencies=[Depends(_rl_social)])
def create_social_post(
    req: SocialPostIn,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """A photo, one or more past workouts, a progress chart, or all together. Workout stats come
    from the player's own saved sessions, never from the request."""
    uid = token_data["id"]
    jpeg: Optional[bytes] = None
    if req.photo_jpeg_base64:
        try:
            jpeg = base64.b64decode(req.photo_jpeg_base64, validate=True)
        except (binascii.Error, ValueError):
            raise _api_error(422, "BAD_PHOTO", "The photo must be base64-encoded") from None
        if len(jpeg) > MAX_PHOTO_BYTES:
            raise _api_error(413, "PHOTO_TOO_LARGE", "The photo must be at most 300 KB")
        if not jpeg.startswith(b"\xff\xd8"):
            raise _api_error(422, "BAD_PHOTO", "The photo must be a JPEG")

    session_ids = list(dict.fromkeys(req.training_session_ids))
    rows = (
        db.query(models.TrainingSession)
        .filter(models.TrainingSession.user_id == uid, models.TrainingSession.id.in_(session_ids or [-1]))
        .all()
    )
    by_id = {r.id: r for r in rows}
    if len(by_id) != len(session_ids):
        raise _api_error(404, "SESSION_NOT_FOUND", "One of those workouts is not yours or no longer exists")
    ordered = [by_id[i] for i in session_ids]
    caption = req.caption.strip()
    if jpeg is None and not ordered and req.chart == "none" and not caption:
        raise _api_error(422, "EMPTY_POST", "Add a photo, a workout, a chart or a caption")

    attachments = [_attachment(db, r) for r in ordered]
    camera = [r for r in ordered if training.BY_KEY.get(r.activity_key, {}).get("kind") == "camera"]
    user = db.query(models.User).filter(models.User.id == uid).one()
    summary = {
        "exercise_key": camera[0].activity_key if len(camera) == 1 and len(ordered) == 1 else None,
        "exercise_name": training.BY_KEY[camera[0].activity_key]["name"]
        if len(camera) == 1 and len(ordered) == 1
        else None,
        "sets": 1,
        "reps_per_set": 0,
        "total_reps": sum(r.reps for r in ordered),
        "hold_s": 0.0,
        "distance_m": round(sum(r.distance_m for r in ordered), 1),
        "duration_s": round(sum(r.duration_s for r in ordered), 1),
        "domain_area_sqkm": 0.0,
        "streak_days": int(user.streak or 0),
        "crystals_earned": 0,
        "xp_earned": 0,
    }
    summary["measure_label"] = _measure_label(summary)
    if not caption and ordered:
        caption = f"{len(ordered)} workout{'s' if len(ordered) > 1 else ''} on Osiris"
    post = models.SocialPost(
        user_id=uid,
        kind="workout" if ordered else "custom",
        caption=caption,
        workout_summary_json=json.dumps(summary, sort_keys=True),
        attachments_json=json.dumps(attachments),
        chart_json=json.dumps(_weekly_chart(db, uid, date.today())) if req.chart == "weekly_progress" else None,
        related_exercise_session_id=ordered[0].exercise_session_id if len(ordered) == 1 else None,
        visibility=req.visibility,
        share_count=0,
    )
    db.add(post)
    db.flush()
    if jpeg is not None:
        db.add(models.PostPhoto(post_id=post.id, token=secrets.token_hex(16), jpeg=jpeg))
    for r in ordered:
        if r.social_post_id is None:
            r.social_post_id = post.id
    db.commit()
    db.refresh(post)
    return _hydrate_posts(db, [post], uid)[0]


@router.delete("/api/v2/social/posts/{post_id}", status_code=204)
def delete_social_post(
    post_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    post = db.query(models.SocialPost).filter(models.SocialPost.id == post_id, models.SocialPost.user_id == uid).first()
    if post is None:
        raise _api_error(404, "POST_NOT_FOUND", "Post not found")
    db.query(models.TrainingSession).filter(models.TrainingSession.social_post_id == post_id).update(
        {models.TrainingSession.social_post_id: None}, synchronize_session=False
    )
    for table in (models.PostReaction, models.PostComment, models.PostPhoto):
        db.query(table).filter(table.post_id == post_id).delete(synchronize_session=False)
    db.delete(post)
    db.commit()
    return Response(status_code=204)


@router.get("/api/v2/social/media/{token}")
def post_photo(token: str, db: Session = Depends(get_db)):
    """Loaded by the app as a plain image URL, so it takes no token header. The 128-bit random token
    is the capability: it is only handed out with a post the viewer may see."""
    if len(token) != 32:
        raise HTTPException(status_code=404, detail="No photo")
    photo = db.query(models.PostPhoto).filter(models.PostPhoto.token == token).first()
    if photo is None:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(photo.jpeg, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


# --- Direct messages -----------------------------------------------------------------


@router.get("/api/v2/social/conversations", response_model=InboxOut)
def inbox(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    blocked = player_safety.blocked_user_ids(db, uid)
    latest: dict[int, models.DirectMessage] = {}
    for m in (
        db.query(models.DirectMessage)
        .filter((models.DirectMessage.sender_id == uid) | (models.DirectMessage.recipient_id == uid))
        .order_by(models.DirectMessage.id.desc())
        .limit(INBOX_SCAN)
    ):
        other = m.recipient_id if m.sender_id == uid else m.sender_id
        if other not in blocked:
            latest.setdefault(other, m)
    unread: dict[int, int] = {
        sender: int(n)
        for sender, n in db.query(models.DirectMessage.sender_id, func.count(models.DirectMessage.id))
        .filter(
            models.DirectMessage.recipient_id == uid,
            models.DirectMessage.read_at.is_(None),
        )
        .group_by(models.DirectMessage.sender_id)
        .all()
    }
    cards = _user_cards(db, uid, list(latest))
    items = [
        ConversationOut(user=cards[other], last_message=_message_out(m, uid), unread_count=int(unread.get(other, 0)))
        for other, m in latest.items()
        if other in cards
    ]
    db.commit()
    return InboxOut(unread_total=sum(c.unread_count for c in items), items=items)


@router.get("/api/v2/social/conversations/{user_id}/messages", response_model=ThreadOut)
def thread(
    user_id: int,
    before_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Oldest first within the page; page back with `before_id` (the first id you hold)."""
    uid = token_data["id"]
    if user_id == uid:
        raise _api_error(422, "SELF_MESSAGE", "You cannot message yourself")
    _visible_player(db, uid, user_id)
    q = db.query(models.DirectMessage).filter(models.DirectMessage.pair_key == _pair_key(uid, user_id))
    if before_id is not None:
        q = q.filter(models.DirectMessage.id < before_id)
    rows = list(reversed(q.order_by(models.DirectMessage.id.desc()).limit(limit).all()))
    card = _user_cards(db, uid, [user_id])[user_id]
    db.commit()
    return ThreadOut(user=card, can_message=_can_message(db, uid, user_id), items=[_message_out(m, uid) for m in rows])


@router.post(
    "/api/v2/social/conversations/{user_id}/messages",
    response_model=DirectMessageOut,
    status_code=201,
    dependencies=[Depends(_rl_social)],
)
def send_message(
    user_id: int,
    req: DirectMessageIn,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    if user_id == uid:
        raise _api_error(422, "SELF_MESSAGE", "You cannot message yourself")
    _visible_player(db, uid, user_id)
    body = req.body.strip()
    if not body:
        raise _api_error(422, "EMPTY_MESSAGE", "Message cannot be empty")
    if not _can_message(db, uid, user_id):
        raise _api_error(403, "NOT_CONNECTED", "You can message players you follow or who follow you")
    already_unread = (
        db.query(models.DirectMessage.id)
        .filter(
            models.DirectMessage.sender_id == uid,
            models.DirectMessage.recipient_id == user_id,
            models.DirectMessage.read_at.is_(None),
        )
        .first()
        is not None
    )
    m = models.DirectMessage(sender_id=uid, recipient_id=user_id, pair_key=_pair_key(uid, user_id), body=body)
    db.add(m)
    if not already_unread:
        # One notification per unread burst, not one per message.
        sender = get_or_create_profile(db, db.query(models.User).filter(models.User.id == uid).one())
        create_notification(
            db,
            user_id=user_id,
            kind="direct_message",
            title="New message",
            body=f"{sender.display_name}: {body[:80]}",
            action_route="social",
        )
    db.commit()
    db.refresh(m)
    return _message_out(m, uid)


@router.post("/api/v2/social/conversations/{user_id}/read", response_model=InboxOut)
def mark_thread_read(
    user_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    db.query(models.DirectMessage).filter(
        models.DirectMessage.sender_id == user_id,
        models.DirectMessage.recipient_id == uid,
        models.DirectMessage.read_at.is_(None),
    ).update({models.DirectMessage.read_at: _now_naive_utc()}, synchronize_session=False)
    db.commit()
    return inbox(db, token_data)

