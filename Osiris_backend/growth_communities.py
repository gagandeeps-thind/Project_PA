"""Growth release G3: communities, team goals, local rankings, and city seasons.

Communities are how Osiris borrows existing trust. A running club, gym, university group,
or workplace gets its own page, a branded leaderboard, a weekly team goal, and featured
challenges. Local rankings group players by the home city they chose, never by GPS.

Privacy: leaderboards show a display name only for players who opted in
(`PlayerProfile.leaderboard_opt_in`). Everyone else appears as "Private runner" so their
position still counts but cannot be tied to them. No location appears anywhere here.

Registered on `main.app` at the bottom; imported from the end of growth_api.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import growth_safety
import models
from growth_api import emit_event, get_or_create_profile
from main import (
    ChallengePublic,
    _api_error,
    _audit,
    _challenge_public,
    _now_naive_utc,
    _refresh_challenge_status,
    app,
    get_active_player,
    get_current_admin,
    get_db,
)
from services import leaderboards as lb
from services import quests as quest_rules

router = APIRouter()

PRIVATE_NAME = "Private runner"
MAX_OWNED_COMMUNITIES = 3
LEADERBOARD_LIMIT = 50
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


# --- schemas ---------------------------------------------------------------------

class CommunityCreate(BaseModel):
    name: str = Field(min_length=3, max_length=60)
    kind: str
    description: Optional[str] = Field(default=None, max_length=500)
    brand_color: Optional[str] = None
    city: Optional[str] = Field(default=None, max_length=60)
    visibility: str = "public"
    weekly_team_goal_km: float = Field(default=100.0, gt=0, le=100_000)
    perk_text: Optional[str] = Field(default=None, max_length=200)


class CommunityUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=500)
    brand_color: Optional[str] = None
    weekly_team_goal_km: Optional[float] = Field(default=None, gt=0, le=100_000)
    perk_text: Optional[str] = Field(default=None, max_length=200)


class JoinRequest(BaseModel):
    join_code: Optional[str] = Field(default=None, max_length=32)


class TeamGoal(BaseModel):
    week_start: str
    goal_km: float
    progress_km: float
    completed: bool
    active_members: int


class CommunityOut(BaseModel):
    slug: str
    name: str
    kind: str
    description: Optional[str] = None
    brand_color: Optional[str] = None
    city: Optional[str] = None
    visibility: str
    verified: bool
    perk_text: Optional[str] = None
    member_count: int
    my_role: Optional[str] = None
    join_code: Optional[str] = None          # only shown to owners and admins
    team_goal: Optional[TeamGoal] = None     # only shown to members


class LeaderboardRow(BaseModel):
    rank: int
    name: str
    points: int
    active_days: int
    distance_km: float
    is_me: bool


class Leaderboard(BaseModel):
    scope: str
    title: str
    period_start: datetime
    period_end: datetime
    rules_version: str
    scoring: str
    rows: List[LeaderboardRow]
    my_row: Optional[LeaderboardRow] = None
    ranked_players: int


class SeasonCreate(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    city: str = Field(min_length=2, max_length=60)
    description: Optional[str] = Field(default=None, max_length=500)
    perk_text: Optional[str] = Field(default=None, max_length=200)
    starts_at: datetime
    ends_at: datetime


class SeasonOut(BaseModel):
    slug: str
    name: str
    city: str
    description: Optional[str] = None
    perk_text: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    status: str
    entered: bool
    participants: int


class CommunityStandingRow(BaseModel):
    rank: int
    slug: str
    name: str
    average_points: int
    entered_members: int
    is_mine: bool


class SeasonLeaderboard(BaseModel):
    season: SeasonOut
    players: Leaderboard
    communities: List[CommunityStandingRow]


class AdminCommunityItem(BaseModel):
    id: int
    slug: str
    name: str
    kind: str
    city: Optional[str] = None
    verified: bool
    status: str
    status_reason: Optional[str] = None
    member_count: int
    owner_user_id: int
    created_at: datetime


class AdminCommunityStatus(BaseModel):
    verified: Optional[bool] = None
    status: Optional[str] = None
    reason: str = Field(min_length=3, max_length=500)


# --- helpers ---------------------------------------------------------------------

def _unique_slug(db: Session, model, base: str) -> str:
    slug = lb.slugify(base)
    candidate = slug
    for _ in range(50):
        if not db.query(model.id).filter(model.slug == candidate).first():
            return candidate
        candidate = f"{slug}-{secrets.token_hex(2)}"
    raise RuntimeError("could not mint a unique slug")


def _get_community(db: Session, slug: str) -> models.Community:
    c = db.query(models.Community).filter(models.Community.slug == slug).first()
    if c is None or c.status != "active":
        raise _api_error(404, "COMMUNITY_NOT_FOUND", "Community not found")
    return c


def _membership(db: Session, community_id: int, user_id: int) -> Optional[models.CommunityMember]:
    return db.query(models.CommunityMember).filter(
        models.CommunityMember.community_id == community_id, models.CommunityMember.user_id == user_id,
    ).first()


def _member_ids(db: Session, community_id: int) -> list[int]:
    return [u for (u,) in db.query(models.CommunityMember.user_id).filter(
        models.CommunityMember.community_id == community_id).all()]


def _daily_by_user(db: Session, user_ids: list[int], start: datetime, end: datetime) -> dict[int, dict]:
    """Verified distance per user per local day inside [start, end)."""
    if not user_ids:
        return {}
    offsets: dict[int, int] = {
        uid: offset for uid, offset in db.query(models.PlayerProfile.user_id, models.PlayerProfile.utc_offset_minutes)
        .filter(models.PlayerProfile.user_id.in_(user_ids)).all()
    }
    rows = db.query(models.RunSession.user_id, models.RunSession.finished_at, models.RunSession.distance_m).filter(
        models.RunSession.user_id.in_(user_ids), models.RunSession.verification_status == "accepted",
        models.RunSession.finished_at >= start, models.RunSession.finished_at < end,
    ).all()
    out: dict[int, dict] = {}
    for uid, finished_at, dist in rows:
        d = quest_rules.local_date(finished_at, offsets.get(uid) or 0)
        days = out.setdefault(uid, {})
        days[d] = days.get(d, 0.0) + float(dist or 0.0)
    return out


def _week_window(now: datetime) -> tuple[datetime, datetime]:
    start_day = quest_rules.week_start(now.date())
    start = datetime(start_day.year, start_day.month, start_day.day)
    return start, start + timedelta(days=7)


def _leaderboard(
    db: Session, *, scope: str, title: str, user_ids: list[int], start: datetime, end: datetime, viewer_id: int,
) -> Leaderboard:
    daily = _daily_by_user(db, user_ids, start, end)
    standings = lb.rank({uid: lb.score(days) for uid, days in daily.items()})
    shown_ids = [s.key for s in standings[:LEADERBOARD_LIMIT]] + [viewer_id]
    profiles = {p.user_id: p for p in db.query(models.PlayerProfile).filter(
        models.PlayerProfile.user_id.in_(shown_ids)).all()}
    hidden = growth_safety.blocked_user_ids(db, viewer_id)

    def row(s: lb.Standing) -> LeaderboardRow:
        p = profiles.get(s.key)
        is_me = s.key == viewer_id
        visible = p is not None and (is_me or (p.leaderboard_opt_in and s.key not in hidden))
        name = p.display_name if visible else PRIVATE_NAME
        return LeaderboardRow(rank=s.rank, name=name, points=s.points, active_days=s.active_days,
                              distance_km=round(s.distance_m / 1000.0, 1), is_me=is_me)

    rows = [row(s) for s in standings[:LEADERBOARD_LIMIT]]
    mine = next((row(s) for s in standings if s.key == viewer_id), None)
    return Leaderboard(scope=scope, title=title, period_start=start, period_end=end,
                       rules_version=lb.LEADERBOARD_RULES_VERSION, scoring=lb.SCORING_EXPLAINER,
                       rows=rows, my_row=mine, ranked_players=len(standings))


def _community_out(db: Session, c: models.Community, viewer_id: int) -> CommunityOut:
    m = _membership(db, c.id, viewer_id)
    members = _member_ids(db, c.id)
    team = None
    if m is not None:
        start, end = _week_window(_now_naive_utc())
        daily = _daily_by_user(db, members, start, end)
        progress = lb.team_progress_km(daily)
        team = TeamGoal(week_start=start.date().isoformat(), goal_km=c.weekly_team_goal_km,
                        progress_km=progress, completed=progress >= c.weekly_team_goal_km,
                        active_members=sum(1 for d in daily.values() if any(v > 0 for v in d.values())))
    return CommunityOut(
        slug=c.slug, name=c.name, kind=c.kind, description=c.description, brand_color=c.brand_color,
        city=c.city, visibility=c.visibility, verified=bool(c.verified), perk_text=c.perk_text,
        member_count=len(members), my_role=m.role if m else None,
        join_code=c.join_code if m is not None and m.role in ("owner", "admin") else None,
        team_goal=team,
    )


def _season_status(s: models.Season, now: datetime) -> str:
    return "upcoming" if now < s.starts_at else ("ended" if now >= s.ends_at else "live")


def _season_out(db: Session, s: models.Season, viewer_id: int) -> SeasonOut:
    entered = db.query(models.SeasonEntry.id).filter(
        models.SeasonEntry.season_id == s.id, models.SeasonEntry.user_id == viewer_id).first() is not None
    return SeasonOut(
        slug=s.slug, name=s.name, city=s.city, description=s.description, perk_text=s.perk_text,
        starts_at=s.starts_at, ends_at=s.ends_at, status=_season_status(s, _now_naive_utc()),
        entered=entered,
        participants=db.query(models.SeasonEntry).filter(models.SeasonEntry.season_id == s.id).count(),
    )


def _get_season(db: Session, slug: str) -> models.Season:
    s = db.query(models.Season).filter(models.Season.slug == slug).first()
    if s is None:
        raise _api_error(404, "SEASON_NOT_FOUND", "Season not found")
    return s


# --- communities -----------------------------------------------------------------

@router.post("/api/v2/communities", response_model=CommunityOut, status_code=201)
def create_community(req: CommunityCreate, db: Session = Depends(get_db),
                           token_data: dict = Depends(get_active_player)):
    """A club, gym, or group organiser creates their community and becomes its owner.
    Organisers need one verified run, which keeps throwaway accounts out."""
    uid = token_data["id"]
    if req.kind not in lb.COMMUNITY_KINDS:
        raise _api_error(422, "INVALID_KIND", f"kind must be one of {', '.join(lb.COMMUNITY_KINDS)}")
    if req.visibility not in ("public", "private"):
        raise _api_error(422, "INVALID_VISIBILITY", "visibility must be public or private")
    if req.brand_color and not HEX_COLOR.match(req.brand_color):
        raise _api_error(422, "INVALID_COLOR", "brand_color must look like #1A2B3C")
    if not db.query(models.RunSession.id).filter(
        models.RunSession.user_id == uid, models.RunSession.verification_status == "accepted").first():
        raise _api_error(403, "NOT_ELIGIBLE", "Complete one verified run before creating a community")
    owned = db.query(models.Community).filter(models.Community.owner_user_id == uid).count()
    if owned >= MAX_OWNED_COMMUNITIES:
        raise _api_error(409, "COMMUNITY_LIMIT", f"You can own up to {MAX_OWNED_COMMUNITIES} communities")
    c = models.Community(
        slug=_unique_slug(db, models.Community, req.name), name=req.name.strip(), kind=req.kind,
        description=req.description, brand_color=req.brand_color,
        city=lb.slugify(req.city) if req.city else None, visibility=req.visibility,
        join_code=secrets.token_hex(3).upper() if req.visibility == "private" else None,
        weekly_team_goal_km=req.weekly_team_goal_km, perk_text=req.perk_text, owner_user_id=uid,
    )
    db.add(c)
    db.flush()
    db.add(models.CommunityMember(community_id=c.id, user_id=uid, role="owner"))
    _audit(db, actor_type="player", actor_id=uid, action="community.created",
           entity_type="community", entity_id=c.id, details={"kind": c.kind, "visibility": c.visibility})
    db.commit()
    return _community_out(db, c, uid)


@router.get("/api/v2/communities", response_model=List[CommunityOut])
def list_communities(city: Optional[str] = None, kind: Optional[str] = None,
                           db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Public communities, optionally in one city or of one kind. Verified first."""
    q = db.query(models.Community).filter(models.Community.status == "active",
                                          models.Community.visibility == "public")
    if city:
        q = q.filter(models.Community.city == lb.slugify(city))
    if kind:
        q = q.filter(models.Community.kind == kind)
    rows = q.order_by(models.Community.verified.desc(), models.Community.name.asc()).limit(100).all()
    return [_community_out(db, c, token_data["id"]) for c in rows]


@router.get("/api/v2/me/communities", response_model=List[CommunityOut])
def my_communities(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    rows = (db.query(models.Community)
            .join(models.CommunityMember, models.CommunityMember.community_id == models.Community.id)
            .filter(models.CommunityMember.user_id == uid, models.Community.status == "active").all())
    return [_community_out(db, c, uid) for c in rows]


@router.get("/api/v2/communities/{slug}", response_model=CommunityOut)
def get_community(slug: str, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    c = _get_community(db, slug)
    if c.visibility == "private" and _membership(db, c.id, token_data["id"]) is None:
        raise _api_error(404, "COMMUNITY_NOT_FOUND", "Community not found")
    return _community_out(db, c, token_data["id"])


@router.patch("/api/v2/communities/{slug}", response_model=CommunityOut)
def update_community(slug: str, req: CommunityUpdate, db: Session = Depends(get_db),
                           token_data: dict = Depends(get_active_player)):
    c = _get_community(db, slug)
    m = _membership(db, c.id, token_data["id"])
    if m is None or m.role not in ("owner", "admin"):
        raise _api_error(403, "NOT_COMMUNITY_ADMIN", "Only community owners and admins can edit it")
    if req.brand_color is not None and not HEX_COLOR.match(req.brand_color):
        raise _api_error(422, "INVALID_COLOR", "brand_color must look like #1A2B3C")
    for field in ("description", "brand_color", "weekly_team_goal_km", "perk_text"):
        value = getattr(req, field)
        if value is not None:
            setattr(c, field, value)
    db.commit()
    return _community_out(db, c, token_data["id"])


@router.post("/api/v2/communities/{slug}/join", response_model=CommunityOut)
def join_community(slug: str, req: JoinRequest, db: Session = Depends(get_db),
                         token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    c = _get_community(db, slug)
    if _membership(db, c.id, uid) is None:
        if c.visibility == "private" and (not req.join_code or req.join_code.strip().upper() != c.join_code):
            raise _api_error(403, "JOIN_CODE_REQUIRED", "This community needs a join code from its organiser")
        db.add(models.CommunityMember(community_id=c.id, user_id=uid, role="member"))
        emit_event(db, "community_joined", user_id=uid, properties={"kind": c.kind})
        db.commit()
    return _community_out(db, c, uid)


@router.post("/api/v2/communities/{slug}/leave", status_code=204)
def leave_community(slug: str, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    c = _get_community(db, slug)
    m = _membership(db, c.id, token_data["id"])
    if m is None:
        return
    if m.role == "owner":
        raise _api_error(409, "OWNER_CANNOT_LEAVE", "Owners cannot leave; ask support to transfer ownership")
    db.delete(m)
    db.commit()


@router.get("/api/v2/communities/{slug}/leaderboard", response_model=Leaderboard)
def community_leaderboard(slug: str, db: Session = Depends(get_db),
                                token_data: dict = Depends(get_active_player)):
    """This week's branded leaderboard. Members only."""
    c = _get_community(db, slug)
    if _membership(db, c.id, token_data["id"]) is None:
        raise _api_error(403, "MEMBERS_ONLY", "Join this community to see its leaderboard")
    start, end = _week_window(_now_naive_utc())
    return _leaderboard(db, scope="community", title=f"{c.name}: this week", user_ids=_member_ids(db, c.id),
                        start=start, end=end, viewer_id=token_data["id"])


@router.post("/api/v2/communities/{slug}/challenges/{challenge_id}", status_code=201)
def feature_challenge(slug: str, challenge_id: int, db: Session = Depends(get_db),
                            token_data: dict = Depends(get_active_player)):
    """Owners and admins feature an open challenge as their community's branded challenge."""
    uid = token_data["id"]
    c = _get_community(db, slug)
    m = _membership(db, c.id, uid)
    if m is None or m.role not in ("owner", "admin"):
        raise _api_error(403, "NOT_COMMUNITY_ADMIN", "Only community owners and admins can feature challenges")
    ch = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if ch is None:
        raise _api_error(404, "CHALLENGE_NOT_FOUND", "Challenge not found")
    _refresh_challenge_status(db, ch)
    if ch.status != "open":
        raise _api_error(409, "CHALLENGE_NOT_OPEN", f"Challenge is {ch.status}")
    if not db.query(models.CommunityChallenge.id).filter(
        models.CommunityChallenge.community_id == c.id, models.CommunityChallenge.challenge_id == ch.id).first():
        db.add(models.CommunityChallenge(community_id=c.id, challenge_id=ch.id, added_by_user_id=uid))
        _audit(db, actor_type="player", actor_id=uid, action="community.challenge_featured",
               entity_type="community", entity_id=c.id, details={"challenge_id": ch.id})
    db.commit()
    return {"community": c.slug, "challenge_id": ch.id}


@router.get("/api/v2/communities/{slug}/challenges", response_model=List[ChallengePublic])
def community_challenges(slug: str, db: Session = Depends(get_db),
                               token_data: dict = Depends(get_active_player)):
    c = _get_community(db, slug)
    if c.visibility == "private" and _membership(db, c.id, token_data["id"]) is None:
        raise _api_error(404, "COMMUNITY_NOT_FOUND", "Community not found")
    rows = (db.query(models.Challenge, models.Course)
            .join(models.CommunityChallenge, models.CommunityChallenge.challenge_id == models.Challenge.id)
            .join(models.Course, models.Course.id == models.Challenge.course_id)
            .filter(models.CommunityChallenge.community_id == c.id).all())
    out = []
    now = _now_naive_utc()
    for ch, course in rows:
        _refresh_challenge_status(db, ch, now)
        if ch.status == "open" and course.status == "active":
            out.append(_challenge_public(db, ch, course, token_data["id"]))
    db.commit()
    return out


# --- local rankings --------------------------------------------------------------

@router.get("/api/v2/leaderboards/local", response_model=Leaderboard)
def local_leaderboard(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """This week's ranking among players who chose the same home city."""
    uid = token_data["id"]
    user = db.query(models.User).filter(models.User.id == uid).first()
    profile = get_or_create_profile(db, user)
    db.commit()
    if not profile.city:
        raise _api_error(409, "CITY_REQUIRED", "Choose your home city in your profile to see local rankings")
    ids = [u for (u,) in db.query(models.PlayerProfile.user_id).filter(
        models.PlayerProfile.city == profile.city).all()]
    suspended = {u for (u,) in db.query(models.User.id).filter(
        models.User.id.in_(ids), models.User.suspended_at.isnot(None)).all()}
    start, end = _week_window(_now_naive_utc())
    return _leaderboard(db, scope="city", title=f"{profile.city}: this week",
                        user_ids=[u for u in ids if u not in suspended], start=start, end=end, viewer_id=uid)


# --- seasons ---------------------------------------------------------------------

@router.get("/api/v2/seasons", response_model=List[SeasonOut])
def list_seasons(city: Optional[str] = None, db: Session = Depends(get_db),
                       token_data: dict = Depends(get_active_player)):
    """Live and upcoming seasons, for one city or the player's home city."""
    uid = token_data["id"]
    if city is None:
        p = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == uid).first()
        city = p.city if p else None
    q = db.query(models.Season).filter(models.Season.ends_at > _now_naive_utc())
    if city:
        q = q.filter(models.Season.city == lb.slugify(city))
    return [_season_out(db, s, uid) for s in q.order_by(models.Season.starts_at.asc()).all()]


@router.post("/api/v2/seasons/{slug}/join", response_model=SeasonOut)
def join_season(slug: str, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    s = _get_season(db, slug)
    if _season_status(s, _now_naive_utc()) == "ended":
        raise _api_error(409, "SEASON_ENDED", "This season has ended")
    if not db.query(models.SeasonEntry.id).filter(
        models.SeasonEntry.season_id == s.id, models.SeasonEntry.user_id == uid).first():
        db.add(models.SeasonEntry(season_id=s.id, user_id=uid))
        emit_event(db, "season_joined", user_id=uid, properties={"season": s.slug})
        db.commit()
    return _season_out(db, s, uid)


@router.get("/api/v2/seasons/{slug}/leaderboard", response_model=SeasonLeaderboard)
def season_leaderboard(slug: str, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    s = _get_season(db, slug)
    entrants = [u for (u,) in db.query(models.SeasonEntry.user_id).filter(models.SeasonEntry.season_id == s.id).all()]
    end = min(s.ends_at, _now_naive_utc())
    players = _leaderboard(db, scope="season", title=s.name, user_ids=entrants,
                           start=s.starts_at, end=max(end, s.starts_at), viewer_id=uid)
    players.period_end = s.ends_at

    daily = _daily_by_user(db, entrants, s.starts_at, max(end, s.starts_at))
    player_scores = {u: lb.score(daily.get(u, {})) for u in entrants}
    communities = db.query(models.Community).filter(
        models.Community.city == s.city, models.Community.status == "active").all()
    members = {c.id: _member_ids(db, c.id) for c in communities}
    standings = lb.rank(lb.community_season_scores(members, player_scores))
    by_id = {c.id: c for c in communities}
    mine = {c for c, uids in members.items() if uid in uids}
    rows = [
        CommunityStandingRow(
            rank=st.rank, slug=by_id[st.key].slug, name=by_id[st.key].name, average_points=st.points,
            entered_members=sum(1 for u in members[st.key] if u in player_scores), is_mine=st.key in mine,
        )
        for st in standings
        if by_id[st.key].visibility == "public" or st.key in mine
    ]
    return SeasonLeaderboard(season=_season_out(db, s, uid), players=players, communities=rows)


# --- admin -----------------------------------------------------------------------

@router.post("/api/v2/admin/seasons", response_model=SeasonOut, status_code=201)
def admin_create_season(req: SeasonCreate, db: Session = Depends(get_db),
                              admin: dict = Depends(get_current_admin)):
    starts = req.starts_at.replace(tzinfo=None)
    ends = req.ends_at.replace(tzinfo=None)
    if ends <= starts or ends - starts > timedelta(days=120):
        raise _api_error(422, "INVALID_WINDOW", "A season must end after it starts and last at most 120 days")
    s = models.Season(slug=_unique_slug(db, models.Season, req.name), name=req.name.strip(),
                      city=lb.slugify(req.city), description=req.description, perk_text=req.perk_text,
                      starts_at=starts, ends_at=ends)
    db.add(s)
    db.flush()
    _audit(db, actor_type="admin", actor_id=admin["id"], action="season.created",
           entity_type="season", entity_id=s.id, details={"city": s.city})
    db.commit()
    return _season_out(db, s, -1)


@router.get("/api/v2/admin/communities", response_model=List[AdminCommunityItem])
def admin_list_communities(db: Session = Depends(get_db), _admin: dict = Depends(get_current_admin)):
    rows = db.query(models.Community).order_by(models.Community.created_at.desc()).limit(500).all()
    return [AdminCommunityItem(
        id=c.id, slug=c.slug, name=c.name, kind=c.kind, city=c.city, verified=bool(c.verified),
        status=c.status, status_reason=c.status_reason, member_count=len(_member_ids(db, c.id)),
        owner_user_id=c.owner_user_id, created_at=c.created_at,
    ) for c in rows]


@router.post("/api/v2/admin/communities/{community_id}/status", response_model=AdminCommunityItem)
def admin_community_status(community_id: int, req: AdminCommunityStatus, db: Session = Depends(get_db),
                                 admin: dict = Depends(get_current_admin)):
    """Verify a real organisation, or suspend an abusive community. Reason required."""
    c = db.query(models.Community).filter(models.Community.id == community_id).first()
    if c is None:
        raise _api_error(404, "COMMUNITY_NOT_FOUND", "Community not found")
    if req.status is not None and req.status not in ("active", "suspended"):
        raise _api_error(422, "INVALID_STATUS", "status must be active or suspended")
    if req.verified is not None:
        c.verified = req.verified
    if req.status is not None:
        c.status = req.status
    c.status_reason = req.reason
    _audit(db, actor_type="admin", actor_id=admin["id"], action="community.status_changed",
           entity_type="community", entity_id=c.id,
           details={"verified": c.verified, "status": c.status, "reason": req.reason})
    db.commit()
    return AdminCommunityItem(
        id=c.id, slug=c.slug, name=c.name, kind=c.kind, city=c.city, verified=bool(c.verified),
        status=c.status, status_reason=c.status_reason, member_count=len(_member_ids(db, c.id)),
        owner_user_id=c.owner_user_id, created_at=c.created_at,
    )


app.include_router(router)
