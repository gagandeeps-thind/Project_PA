"""Admin trust console (PRD-010): review queue, challenge and course moderation, suspensions, audit log."""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from core.clock import _now_naive_utc
from core.errors import _api_error
from core.security import get_current_admin
from database import get_db
from schemas import (
    AdminChallengeAction,
    AdminChallengeItem,
    AdminCourseStatus,
    AdminReason,
    AdminReviewDecision,
    AdminUserStatus,
    AttemptSummary,
    AuditEventOut,
    ReviewQueueItem,
)
from services.audit import _audit
from services.challenge_store import _apply_attempt_outcome, _attempt_summary, _get_challenge, _refresh_challenge_status
from services.progression import _adjust_xp


router = APIRouter()


def _admin_attempt_counts(db: Session, challenge_ids: "list[int]") -> dict[int, int]:
    rows = db.query(models.ChallengeAttempt.challenge_id, func.count(models.ChallengeAttempt.id)).filter(
        models.ChallengeAttempt.challenge_id.in_(list(challenge_ids) or [-1]),
    ).group_by(models.ChallengeAttempt.challenge_id).all()
    return {cid: n for cid, n in rows}


def _admin_challenge_item(db: Session, ch: models.Challenge,
                          attempt_counts: Optional[dict[int, int]] = None) -> AdminChallengeItem:
    if attempt_counts is None:
        attempt_counts = _admin_attempt_counts(db, [ch.id])
    return AdminChallengeItem(
        id=ch.id, title=ch.title, status=ch.status, status_reason=ch.status_reason,
        creator_id=ch.creator_id, course_id=ch.course_id,
        attempt_count=attempt_counts.get(ch.id, 0),
        closes_at=ch.closes_at, created_at=ch.created_at,
    )


@router.get("/api/v2/admin/review-queue", response_model=List[ReviewQueueItem])
def admin_review_queue(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    rows = (
        db.query(models.ChallengeAttempt, models.Challenge)
        .join(models.Challenge, models.Challenge.id == models.ChallengeAttempt.challenge_id)
        .filter(models.ChallengeAttempt.status == "review_required")
        .order_by(models.ChallengeAttempt.submitted_at.asc(), models.ChallengeAttempt.id.asc())
        .offset(offset).limit(limit)
        .all()
    )
    return [
        ReviewQueueItem(
            attempt_id=a.id, challenge_id=ch.id, challenge_title=ch.title, user_id=a.user_id,
            run_id=a.run_session_id, elapsed_seconds=a.elapsed_seconds,
            target_seconds=ch.target_seconds, course_coverage=a.course_coverage,
            submitted_at=a.submitted_at,
        )
        for a, ch in rows
    ]


@router.post("/api/v2/admin/attempts/{attempt_id}/review", response_model=AttemptSummary)
def admin_review_attempt(
    attempt_id: int,
    req: AdminReviewDecision,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    attempt = db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.id == attempt_id).first()
    if attempt is None:
        raise _api_error(404, "ATTEMPT_NOT_FOUND", "Attempt not found")
    if attempt.status != "review_required":
        raise _api_error(409, "NOT_IN_REVIEW", f"Attempt is {attempt.status}")
    ch = _get_challenge(db, attempt.challenge_id)
    attempt.reviewed_by_admin_id = token_data["id"]
    attempt.review_note = req.note
    if req.decision == "accept":
        attempt.status = "accepted"
        attempt.outcome = "won" if (attempt.elapsed_seconds or 0) < ch.target_seconds else "lost"
        attempt.reason_codes_json = "[]"
        if ch.status != "voided":
            _apply_attempt_outcome(db, attempt, ch)
    else:
        attempt.status = "rejected"
        attempt.reason_codes_json = json.dumps(["REVIEW_REJECTED"])
        attempt.decided_at = _now_naive_utc()
    _audit(db, actor_type="admin", actor_id=token_data["id"], action="attempt.reviewed",
           entity_type="challenge_attempt", entity_id=attempt.id,
           details={"decision": req.decision, "note": req.note, "outcome": attempt.outcome})
    _refresh_challenge_status(db, ch)
    db.commit()
    db.refresh(attempt)
    return _attempt_summary(attempt, ch)


@router.get("/api/v2/admin/challenges", response_model=List[AdminChallengeItem])
def admin_list_challenges(
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    q = db.query(models.Challenge)
    if status:
        q = q.filter(models.Challenge.status == status)
    challenges = q.order_by(models.Challenge.created_at.desc(), models.Challenge.id.desc()).offset(offset).limit(
        limit).all()
    counts = _admin_attempt_counts(db, [ch.id for ch in challenges])
    return [_admin_challenge_item(db, ch, counts) for ch in challenges]


@router.post("/api/v2/admin/challenges/{challenge_id}/status", response_model=AdminChallengeItem)
def admin_challenge_status(
    challenge_id: int,
    req: AdminChallengeAction,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    """Suspend, resume, or void a challenge without database edits (PRD-010). Voiding
    reverses every XP award the challenge produced and marks all attempts voided."""
    ch = _get_challenge(db, challenge_id)
    if req.action == "suspend":
        if ch.status not in ("open", "closed"):
            raise _api_error(409, "INVALID_TRANSITION", f"Cannot suspend a {ch.status} challenge")
        ch.status = "suspended"
    elif req.action == "resume":
        if ch.status != "suspended":
            raise _api_error(409, "INVALID_TRANSITION", f"Cannot resume a {ch.status} challenge")
        ch.status = "open"
        _refresh_challenge_status(db, ch)
    else:
        if ch.status == "voided":
            raise _api_error(409, "INVALID_TRANSITION", "Challenge is already voided")
        attempts = db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.challenge_id == ch.id).all()
        defender = db.query(models.User).filter(models.User.id == ch.creator_id).first()
        for a in attempts:
            if a.xp_awarded:
                challenger = db.query(models.User).filter(models.User.id == a.user_id).first()
                if challenger is not None:
                    _adjust_xp(challenger, -a.xp_awarded)
            if a.defender_xp_awarded and defender is not None:
                _adjust_xp(defender, -a.defender_xp_awarded)
            a.outcome = "voided"
            a.decided_at = a.decided_at or _now_naive_utc()
        ch.status = "voided"
    ch.status_reason = req.reason
    _audit(db, actor_type="admin", actor_id=token_data["id"], action=f"challenge.{req.action}",
           entity_type="challenge", entity_id=ch.id, details={"reason": req.reason, "status": ch.status})
    db.commit()
    db.refresh(ch)
    return _admin_challenge_item(db, ch)


@router.post("/api/v2/admin/courses/{course_id}/suspend", response_model=AdminCourseStatus)
def admin_suspend_course(
    course_id: int,
    req: AdminReason,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    """Take a course off the map (e.g. unsafe or sensitive location) and suspend its live
    challenges."""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if course is None:
        raise _api_error(404, "COURSE_NOT_FOUND", "Course not found")
    course.status = "suspended"
    live = db.query(models.Challenge).filter(
        models.Challenge.course_id == course.id, models.Challenge.status.in_(("open", "closed")),
    ).all()
    for ch in live:
        ch.status = "suspended"
        ch.status_reason = f"Course suspended: {req.reason}"
    _audit(db, actor_type="admin", actor_id=token_data["id"], action="course.suspend",
           entity_type="course", entity_id=course.id,
           details={"reason": req.reason, "suspended_challenges": [c.id for c in live]})
    db.commit()
    return AdminCourseStatus(id=course.id, status=course.status, suspended_challenges=len(live))


def _set_user_suspension(db: Session, user_id: int, admin_id: int, reason: Optional[str]) -> AdminUserStatus:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise _api_error(404, "USER_NOT_FOUND", "User not found")
    user.suspended_at = _now_naive_utc() if reason else None
    user.suspension_reason = reason
    _audit(db, actor_type="admin", actor_id=admin_id,
           action="user.suspend" if reason else "user.unsuspend",
           entity_type="user", entity_id=user.id, details={"reason": reason})
    db.commit()
    return AdminUserStatus(user_id=user.id, email=user.email, suspended=reason is not None,
                           suspension_reason=reason)


@router.post("/api/v2/admin/users/{user_id}/suspend", response_model=AdminUserStatus)
def admin_suspend_user(
    user_id: int,
    req: AdminReason,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    return _set_user_suspension(db, user_id, token_data["id"], req.reason)


@router.post("/api/v2/admin/users/{user_id}/unsuspend", response_model=AdminUserStatus)
def admin_unsuspend_user(
    user_id: int,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    return _set_user_suspension(db, user_id, token_data["id"], None)


@router.get("/api/v2/admin/audit-events", response_model=List[AuditEventOut])
def admin_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 100,
    before_id: Optional[int] = None,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_current_admin),
):
    """Newest first. For the next page pass the last id shown as `before_id`."""
    q = db.query(models.AuditEvent)
    if before_id is not None:
        q = q.filter(models.AuditEvent.id < before_id)
    if entity_type:
        q = q.filter(models.AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(models.AuditEvent.entity_id == entity_id)
    if action:
        q = q.filter(models.AuditEvent.action == action)
    rows = q.order_by(models.AuditEvent.id.desc()).limit(min(max(limit, 1), 500)).all()
    return [
        AuditEventOut(
            id=r.id, actor_type=r.actor_type, actor_id=r.actor_id, action=r.action,
            entity_type=r.entity_type, entity_id=r.entity_id,
            details=json.loads(r.details_json or "{}"), created_at=r.created_at,
        )
        for r in rows
    ]
