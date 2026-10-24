"""Discover and Social hubs: the challenge hub sections and the global leaderboards.

Challenge hub sections (Discover tab):
  live       open challenges inside their window, with how many players joined
  upcoming   open challenges whose window has not started, with the start time
  community  open challenges featured by an active public community
  finished   challenges that closed in the last 14 days, with the top finishers and the XP paid

Global boards (Social tab), this week or all time, from verified data only:
  distance   verified run/walk distance
  pace       best Riegel 5 km-equivalent time from one verified run of at least 1 km (lower wins)
  reps       valid reps of one camera-verified exercise (plank: seconds held)
  rewards    XP won from challenges (challenges pay XP and badges only, ADR-005)

Privacy follows the community leaderboards: names only for players who opted in and are not
blocked either way; everyone else is "Private runner". Suspended players are left out.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import growth_safety
import models
from growth_communities import LEADERBOARD_LIMIT, PRIVATE_NAME, _week_window
from core.clock import _now_naive_utc
from core.security import get_active_player
from database import get_db
from schemas import ChallengePublic
from services.challenge_store import _challenge_public, _refresh_challenge_status, ChallengeStats
from services import leaderboards as lb
from services.ttl_cache import TTLCache, ttl_from_env

router = APIRouter()

HUB_LIMIT = 50
FINISHED_WINDOW = timedelta(days=14)
PODIUM = 3

HubSection = Literal["live", "upcoming", "community", "finished"]
Board = Literal["distance", "pace", "reps", "rewards"]
Period = Literal["week", "all"]

# Every board scans all verified data for its period (about 300 ms at 100k runs), and every
# player opening the Social tab asks for one. Other players' values may lag a minute; the
# viewer's own value is always read fresh, so a run just finished shows at once.
BOARD_CACHE = TTLCache(ttl_from_env("OSIRIS_LEADERBOARD_CACHE_SECONDS", 60))


class Finisher(BaseModel):
    rank: int
    name: str
    elapsed_seconds: float


class HubChallenge(BaseModel):
    challenge: ChallengePublic
    participants: int
    starts_in_seconds: Optional[int] = None      # upcoming only
    community_name: Optional[str] = None         # community only
    winners: List[Finisher] = []                 # finished only
    xp_paid: Optional[int] = None                # finished only


class HubSectionOut(BaseModel):
    section: str
    items: List[HubChallenge]


class BoardRow(BaseModel):
    rank: int
    name: str
    value: float
    is_me: bool


class GlobalBoard(BaseModel):
    board: str
    period: str
    exercise: Optional[str] = None
    unit: str
    lower_is_better: bool
    explainer: str
    rows: List[BoardRow]
    my_row: Optional[BoardRow] = None
    ranked_players: int


def _names(db: Session, user_ids: list[int], viewer_id: int) -> dict[int, str]:
    hidden = growth_safety.blocked_user_ids(db, viewer_id)
    profiles = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(user_ids or [-1])).all()
    out = {uid: PRIVATE_NAME for uid in user_ids}
    for p in profiles:
        if p.user_id == viewer_id or (p.leaderboard_opt_in and p.user_id not in hidden):
            out[p.user_id] = p.display_name
    return out


def _participants(db: Session, challenge_ids: list[int]) -> dict[int, int]:
    rows = db.query(models.ChallengeAttempt.challenge_id, func.count(models.ChallengeAttempt.id)).filter(
        models.ChallengeAttempt.challenge_id.in_(challenge_ids or [-1])).group_by(models.ChallengeAttempt.challenge_id).all()
    return {cid: n for cid, n in rows}


def _item(ch: models.Challenge, course: models.Course, db: Session, viewer_id: int,
          participants: dict[int, int], stats: ChallengeStats) -> HubChallenge:
    return HubChallenge(challenge=_challenge_public(db, ch, course, viewer_id, stats=stats),
                        participants=participants.get(ch.id, 0))


@router.get("/api/v2/challenge-hub", response_model=HubSectionOut)
def challenge_hub(
    section: HubSection,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    now = _now_naive_utc()
    blocked = growth_safety.blocked_user_ids(db, uid)
    q = db.query(models.Challenge).filter(models.Challenge.creator_id.notin_(blocked or {-1}))
    community_of: dict[int, str] = {}

    if section == "finished":
        candidates = q.filter(models.Challenge.status.in_(("open", "closed", "settled")),
                              models.Challenge.closes_at <= now, models.Challenge.closes_at >= now - FINISHED_WINDOW)
        challenges = candidates.order_by(models.Challenge.closes_at.desc()).limit(HUB_LIMIT).all()
    else:
        open_now = q.filter(models.Challenge.status == "open", models.Challenge.closes_at > now)
        if section == "live":
            shown = open_now.filter(models.Challenge.opens_at <= now).order_by(models.Challenge.closes_at.asc())
        elif section == "upcoming":
            shown = open_now.filter(models.Challenge.opens_at > now).order_by(models.Challenge.opens_at.asc())
        else:
            featured = db.query(models.CommunityChallenge.challenge_id, models.Community.name).join(
                models.Community, models.Community.id == models.CommunityChallenge.community_id,
            ).filter(models.Community.status == "active", models.Community.visibility == "public").all()
            community_of = {cid: name for cid, name in featured}
            shown = open_now.filter(models.Challenge.id.in_(list(community_of) or [-1])).order_by(
                models.Challenge.closes_at.asc())
        challenges = shown.limit(HUB_LIMIT).all()

    # Settling a challenge is committed after the response is built: committing first expires every
    # loaded challenge, and each one is then re-fetched while it is serialised.
    changed = any([_refresh_challenge_status(db, ch, now) for ch in challenges])
    # Everything a section shows is loaded per list, not per challenge (a fixed number of queries
    # for any HUB_LIMIT; the per-challenge version ran 3 queries for every challenge).
    ids = [ch.id for ch in challenges]
    participants = _participants(db, ids)
    stats = ChallengeStats.load(db, ids, uid)
    courses = {c.id: c for c in db.query(models.Course).filter(
        models.Course.id.in_([ch.course_id for ch in challenges] or [-1])).all()}
    results = _results(db, ids, uid) if section == "finished" else {}
    items = []
    for ch in challenges:
        item = _item(ch, courses[ch.course_id], db, uid, participants, stats)
        if section == "upcoming":
            item.starts_in_seconds = max(0, int((ch.opens_at - now).total_seconds()))
        elif section == "community":
            item.community_name = community_of.get(ch.id)
        elif section == "finished":
            item.xp_paid, item.winners = results.get(ch.id, (0, []))
        items.append(item)
    if changed:
        db.commit()
    return HubSectionOut(section=section, items=items)


def _results(db: Session, challenge_ids: list[int], viewer_id: int) -> dict[int, tuple[int, list[Finisher]]]:
    """XP paid out and the podium for each finished challenge, in two queries for the whole list."""
    by_challenge: dict[int, list[models.ChallengeAttempt]] = {cid: [] for cid in challenge_ids}
    for a in db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.challenge_id.in_(challenge_ids or [-1])):
        by_challenge[a.challenge_id].append(a)
    podiums = {
        cid: sorted((a for a in attempts if a.outcome == "won" and a.elapsed_seconds is not None),
                    key=lambda a: (a.elapsed_seconds, a.id))[:PODIUM]
        for cid, attempts in by_challenge.items()
    }
    names = _names(db, sorted({a.user_id for won in podiums.values() for a in won}), viewer_id)
    out = {}
    for cid, attempts in by_challenge.items():
        xp_paid = sum((a.xp_awarded or 0) for a in attempts) + sum((a.defender_xp_awarded or 0) for a in attempts)
        winners = [Finisher(rank=i, name=names[a.user_id], elapsed_seconds=round(a.elapsed_seconds, 1))
                   for i, a in enumerate(podiums[cid], start=1)]
        out[cid] = (xp_paid, winners)
    return out


def _period_start(period: Period, now: datetime) -> Optional[datetime]:
    return _week_window(now)[0] if period == "week" else None


def _active_players(db: Session) -> set[int]:
    return {u for (u,) in db.query(models.User.id).filter(models.User.suspended_at.is_(None)).all()}


def _board_values(db: Session, board: Board, start: Optional[datetime], exercise: str,
                  user_id: Optional[int] = None) -> dict[int, float]:
    """Each player's value on `board` since `start`; only `user_id`'s when given."""
    if board == "distance":
        q = db.query(models.RunSession.user_id, func.sum(models.RunSession.distance_m)).filter(
            models.RunSession.verification_status == "accepted")
        if start is not None:
            q = q.filter(models.RunSession.finished_at >= start)
        if user_id is not None:
            q = q.filter(models.RunSession.user_id == user_id)
        return {u: float(v or 0) / 1000.0 for u, v in q.group_by(models.RunSession.user_id).all()}
    if board == "pace":
        runs = db.query(models.RunSession.user_id, models.RunSession.distance_m,
                        models.RunSession.duration_seconds).filter(
            models.RunSession.verification_status == "accepted",
            models.RunSession.distance_m >= lb.PACE_MIN_DISTANCE_M, models.RunSession.duration_seconds > 0)
        if start is not None:
            runs = runs.filter(models.RunSession.finished_at >= start)
        if user_id is not None:
            runs = runs.filter(models.RunSession.user_id == user_id)
        values: dict[int, float] = {}
        for uid, dist, secs in runs.all():
            t = lb.riegel_seconds(float(secs), float(dist))
            values[uid] = min(values.get(uid, t), t)
        return values
    if board == "reps":
        metric = models.ExerciseSession.hold_s if exercise == "plank" else models.ExerciseSession.reps_valid
        q = db.query(models.ExerciseSession.user_id, func.sum(metric)).filter(
            models.ExerciseSession.status == "verified", models.ExerciseSession.exercise_key == exercise)
        if start is not None:
            q = q.filter(models.ExerciseSession.created_at >= start)
        if user_id is not None:
            q = q.filter(models.ExerciseSession.user_id == user_id)
        return {u: float(v or 0) for u, v in q.group_by(models.ExerciseSession.user_id).all()}
    wins = db.query(models.ChallengeAttempt.user_id, func.sum(models.ChallengeAttempt.xp_awarded)).filter(
        models.ChallengeAttempt.outcome == "won")
    if start is not None:
        wins = wins.filter(models.ChallengeAttempt.decided_at >= start)
    if user_id is not None:
        wins = wins.filter(models.ChallengeAttempt.user_id == user_id)
    return {u: float(v or 0) for u, v in wins.group_by(models.ChallengeAttempt.user_id).all()}


def _active_board_values(db: Session, board: Board, start: Optional[datetime], exercise: str) -> dict[int, float]:
    allowed = _active_players(db)
    return {u: v for u, v in _board_values(db, board, start, exercise).items() if u in allowed}


BOARD_META = {
    "distance": ("km", "Verified run and walk distance."),
    "pace": ("s", "Best verified run of 1 km or more, converted to a 5 km time with Riegel's formula."),
    "reps": ("reps", "Valid reps counted on camera and verified."),
    "rewards": ("xp", "XP won from challenges."),
}


@router.get("/api/v2/leaderboards/global", response_model=GlobalBoard)
def global_leaderboard(
    board: Board,
    period: Period = "week",
    exercise: str = Query(default="pushup", pattern="^(pushup|squat|pullup|plank)$"),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    start = _period_start(period, _now_naive_utc())
    ascending = board == "pace"
    # Sorted once per cache fill; the viewer is active (get_active_player), so their fresh value
    # always stands in for the cached one.
    ranking: lb.RankedBoard = BOARD_CACHE.get_or_compute(
        (board, start, exercise),
        lambda: lb.RankedBoard(_active_board_values(db, board, start, exercise), ascending=ascending))
    fresh = _board_values(db, board, start, exercise, user_id=uid).get(uid)
    shown, my_rank, ranked_players = ranking.view(uid, fresh, LEADERBOARD_LIMIT)
    names = _names(db, [k for k, _, _ in shown] + [uid], uid)

    def row(key: int, value: float, position: int) -> BoardRow:
        return BoardRow(rank=position, name=names.get(key, PRIVATE_NAME), value=round(value, 1), is_me=key == uid)

    mine = row(*my_rank) if my_rank is not None else None
    unit, explainer = BOARD_META[board]
    if board == "reps" and exercise == "plank":
        unit, explainer = "s", "Seconds of verified plank hold."
    return GlobalBoard(
        board=board, period=period, exercise=exercise if board == "reps" else None, unit=unit,
        lower_is_better=ascending, explainer=explainer, rows=[row(*r) for r in shown], my_row=mine,
        ranked_players=ranked_players,
    )
