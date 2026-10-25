"""Database-backed challenge operations shared by routers and jobs: status refresh,
settlement of attempts, and the batched read models of courses and challenges."""
import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from core.clock import _now_naive_utc
from core.errors import _api_error
from schemas import AttemptSummary, ChallengePublic, CourseSummary
from services import challenges as challenge_rules
from services.audit import _audit
from services.progression import _adjust_xp, _award_badge



def _run_points(db: Session, run_id: int) -> "list[tuple[float, float, int]]":
    rows = (
        db.query(models.RoutePoint)
        .filter(models.RoutePoint.run_session_id == run_id)
        .order_by(models.RoutePoint.sequence.asc())
        .all()
    )
    return [(r.lat, r.lng, r.t_ms) for r in rows]


def _course_route(course: models.Course) -> "list[tuple[float, float]]":
    return [(p[0], p[1]) for p in json.loads(course.route_json)]


def _open_challenge_ids(db: Session, course_ids: list[int]) -> dict[int, int]:
    """course id -> the id of one open challenge on it, for many courses in one query."""
    rows = db.query(models.Challenge.course_id, func.min(models.Challenge.id)).filter(
        models.Challenge.course_id.in_(course_ids or [-1]), models.Challenge.status == "open",
    ).group_by(models.Challenge.course_id).all()
    return {course_id: challenge_id for course_id, challenge_id in rows}


def _course_summary(db: Session, course: models.Course,
                    open_ids: Optional[dict[int, int]] = None) -> CourseSummary:
    if open_ids is None:
        open_ids = _open_challenge_ids(db, [course.id])
    return CourseSummary(
        id=course.id, name=course.name, status=course.status, version=course.version,
        rules_version=course.rules_version, distance_m=round(course.distance_m, 2),
        benchmark_seconds=round(course.benchmark_seconds, 2), is_loop=bool(course.is_loop),
        public_lat=course.public_lat, public_lng=course.public_lng,
        route=[list(p) for p in _course_route(course)],
        open_challenge_id=open_ids.get(course.id), created_at=course.created_at,
    )


def _attempt_summary(attempt: models.ChallengeAttempt, challenge: models.Challenge) -> AttemptSummary:
    return AttemptSummary(
        id=attempt.id, challenge_id=attempt.challenge_id, status=attempt.status,
        outcome=attempt.outcome, run_id=attempt.run_session_id,
        elapsed_seconds=attempt.elapsed_seconds, target_seconds=challenge.target_seconds,
        course_coverage=attempt.course_coverage,
        reason_codes=json.loads(attempt.reason_codes_json or "[]"),
        xp_awarded=attempt.xp_awarded or 0, terms_hash=attempt.terms_hash,
        joined_at=attempt.joined_at, decided_at=attempt.decided_at,
    )


def _refresh_challenge_status(db: Session, ch: models.Challenge, now: Optional[datetime] = None) -> bool:
    """Advance open -> closed -> settled by the clock. Returns True if anything changed; the
    caller commits. Settlement waits out the submission grace period and any pending review."""
    now = now or _now_naive_utc()
    changed = False
    if ch.status == "open" and now >= ch.closes_at:
        ch.status = "closed"
        _audit(db, actor_type="system", actor_id=None, action="challenge.closed",
               entity_type="challenge", entity_id=ch.id)
        changed = True
    grace = timedelta(hours=challenge_rules.SUBMISSION_GRACE_HOURS)
    if ch.status == "closed" and now >= ch.closes_at + grace:
        attempts = db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.challenge_id == ch.id).all()
        if not any(a.status == "review_required" for a in attempts):
            ch.status = "settled"
            ch.settled_at = now
            _audit(db, actor_type="system", actor_id=None, action="challenge.settled",
                   entity_type="challenge", entity_id=ch.id,
                   details={"attempts": len(attempts),
                            "wins": sum(1 for a in attempts if a.outcome == "won")})
            changed = True
    return changed


class ChallengeStats:
    """Per-challenge attempt counts and the viewer's own attempts, loaded for a whole list at once.

    Serialising a list one challenge at a time cost two queries per challenge (the nearby map
    ran 51 queries for 24 challenges); this loads them in two queries for any list size."""

    def __init__(self, attempt_counts: dict[int, int], mine: dict[int, models.ChallengeAttempt]):
        self.attempt_counts = attempt_counts
        self.mine = mine

    @classmethod
    def load(cls, db: Session, challenge_ids: "list[int]", viewer_id: int) -> "ChallengeStats":
        ids = list(challenge_ids) or [-1]
        counts = db.query(models.ChallengeAttempt.challenge_id, func.count(models.ChallengeAttempt.id)).filter(
            models.ChallengeAttempt.challenge_id.in_(ids),
            models.ChallengeAttempt.run_session_id.isnot(None),
        ).group_by(models.ChallengeAttempt.challenge_id).all()
        mine = db.query(models.ChallengeAttempt).filter(
            models.ChallengeAttempt.challenge_id.in_(ids), models.ChallengeAttempt.user_id == viewer_id,
        ).all()
        return cls({cid: n for cid, n in counts}, {a.challenge_id: a for a in mine})


def _challenge_public(
    db: Session, ch: models.Challenge, course: models.Course, viewer_id: int,
    distance_km: Optional[float] = None, stats: Optional[ChallengeStats] = None,
) -> ChallengePublic:
    """Serialise one challenge. List endpoints pass `stats` from ChallengeStats.load so the
    attempt figures cost no extra queries per challenge."""
    if stats is None:
        stats = ChallengeStats.load(db, [ch.id], viewer_id)
    attempt_count = stats.attempt_counts.get(ch.id, 0)
    mine = stats.mine.get(ch.id)
    return ChallengePublic(
        id=ch.id, title=ch.title, status=ch.status, rules_version=ch.rules_version,
        terms_hash=ch.terms_hash, course_distance_m=round(course.distance_m, 2),
        target_seconds=round(ch.target_seconds, 2), entry_crystals=ch.entry_crystals,
        reward_policy=ch.reward_policy, win_xp=ch.win_xp, participation_xp=ch.participation_xp,
        eligibility=ch.eligibility, privacy_mode=ch.privacy_mode, safety_notes=ch.safety_notes,
        opens_at=ch.opens_at, closes_at=ch.closes_at,
        marker_lat=course.public_lat, marker_lng=course.public_lng,
        distance_km=distance_km, attempt_count=attempt_count,
        is_mine=ch.creator_id == viewer_id,
        my_attempt=_attempt_summary(mine, ch) if mine else None,
    )


def _apply_attempt_outcome(db: Session, attempt: models.ChallengeAttempt, ch: models.Challenge) -> None:
    """Award the non-cash rewards for a decided attempt (ADR-005: XP and badges only)."""
    challenger = db.query(models.User).filter(models.User.id == attempt.user_id).first()
    defender = db.query(models.User).filter(models.User.id == ch.creator_id).first()
    if attempt.outcome == "won":
        attempt.xp_awarded = ch.win_xp
        _award_badge(db, attempt.user_id, "FIRST_CHALLENGE_WIN")
    else:
        attempt.xp_awarded = ch.participation_xp
        if defender is not None:
            attempt.defender_xp_awarded = challenge_rules.DEFENSE_XP
            _adjust_xp(defender, challenge_rules.DEFENSE_XP)
            _award_badge(db, defender.id, "FIRST_DEFENSE")
    if challenger is not None:
        _adjust_xp(challenger, attempt.xp_awarded)
    attempt.decided_at = _now_naive_utc()
    import growth_api  # deferred: growth_api imports this module
    growth_api.emit_event(db, "challenge_completed", user_id=attempt.user_id,
                          properties={"challenge_id": ch.id, "outcome": attempt.outcome})


def _get_challenge(db: Session, challenge_id: int) -> models.Challenge:
    ch = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if ch is None:
        raise _api_error(404, "CHALLENGE_NOT_FOUND", "Challenge not found")
    return ch
