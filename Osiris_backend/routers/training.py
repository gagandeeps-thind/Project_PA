# ruff: noqa: B008  (FastAPI dependencies are declared as argument defaults)
"""Start tab: personal training sessions (Train and Challenge), their results and history,
the motivation board and the player's connections. Training never moves crystals or XP."""
import json
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import growth_feed
import models
from core.security import get_active_player
from database import get_db
from growth_social import _display_name
from schemas import (
    Connection,
    MotivationQuote,
    TrainingActivity,
    TrainingPost,
    TrainingProgress,
    TrainingRecord,
    TrainingSegments,
    TrainingSeries,
    TrainingSessionIn,
    TrainingSessionOut,
    TrainingSessions,
    TrainingSummary,
    TrainingWeek,
)
from services import training

router = APIRouter()

STAT_FIELDS = ("hr_avg", "hr_min", "hr_max", "power_avg", "power_min", "power_max",
               "speed_avg", "speed_max", "elev_min", "elev_max")


def _activity(key: str) -> dict:
    activity = training.BY_KEY.get(key)
    if activity is None:
        raise HTTPException(status_code=422, detail="Unknown activity")
    return activity


def _naive_utc(at: datetime) -> datetime:
    return at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at


def _is_pr(db: Session, row: models.TrainingSession) -> bool:
    """Best primary metric of this activity so far, counting only earlier sessions."""
    metric = training.BY_KEY[row.activity_key]["metric"]
    value = training.metric_value(row, metric)
    if value <= 0:
        return False
    column = getattr(models.TrainingSession, metric)
    better = db.query(models.TrainingSession.id).filter(
        models.TrainingSession.user_id == row.user_id,
        models.TrainingSession.activity_key == row.activity_key,
        models.TrainingSession.id < row.id,
        column >= value,
    ).first()
    return better is None


def _out(db: Session, row: models.TrainingSession, with_series: bool = False) -> TrainingSessionOut:
    return TrainingSessionOut(
        id=row.id, activity_key=row.activity_key, mode=row.mode, source=row.source, started_at=row.started_at,
        duration_s=row.duration_s, distance_m=row.distance_m, elevation_gain_m=row.elevation_gain_m, reps=row.reps,
        **{f: getattr(row, f) for f in STAT_FIELDS},
        posted=row.social_post_id is not None, is_pr=_is_pr(db, row),
        series=TrainingSeries(**json.loads(row.series_json or "{}")) if with_series else None,
    )


def _own(db: Session, uid: int, session_id: int) -> models.TrainingSession:
    row = db.query(models.TrainingSession).filter(
        models.TrainingSession.id == session_id, models.TrainingSession.user_id == uid).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@router.get("/api/v2/training/activities", response_model=List[TrainingActivity])
def list_activities(token_data: dict = Depends(get_active_player)):
    return training.ACTIVITIES


@router.post("/api/v2/training/sessions", response_model=TrainingSessionOut, status_code=201)
def upload_session(req: TrainingSessionIn, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    activity = _activity(req.activity_key)
    existing = db.query(models.TrainingSession).filter(
        models.TrainingSession.user_id == uid, models.TrainingSession.client_session_id == req.client_session_id).first()
    if existing is not None:
        return _out(db, existing)

    duration, reps = req.duration_s, 0
    if activity["kind"] == "camera":
        # Reps come only from the server-checked camera set, never from the client.
        if req.exercise_session_id is None:
            raise HTTPException(status_code=422, detail="A camera workout needs its verified set")
        ex = db.query(models.ExerciseSession).filter(models.ExerciseSession.id == req.exercise_session_id).first()
        if ex is None:
            raise HTTPException(status_code=404, detail="Exercise set not found")
        if ex.user_id != uid:
            raise HTTPException(status_code=403, detail="Not your exercise set")
        if ex.exercise_key != req.activity_key:
            raise HTTPException(status_code=422, detail="The set is a different exercise")
        duration, reps = ex.duration_s, ex.reps_valid
    elif req.exercise_session_id is not None:
        raise HTTPException(status_code=422, detail="Only camera workouts link an exercise set")

    if req.distance_m > activity["max_speed_mps"] * duration:
        raise HTTPException(status_code=422, detail="Distance is not plausible for that time")

    series = training.clean_series(req.series.model_dump(), duration, activity["max_speed_mps"])
    started = _naive_utc(req.started_at)
    row = models.TrainingSession(
        user_id=uid, client_session_id=req.client_session_id, activity_key=req.activity_key, mode=req.mode,
        source=req.source, started_at=started, duration_s=round(duration, 1), distance_m=round(req.distance_m, 1),
        reps=reps, exercise_session_id=req.exercise_session_id, series_json=json.dumps(series),
        devices_json=json.dumps([d[:64] for d in req.devices]),
        # The player's own calendar day, so weekly totals follow their week, not UTC's.
        local_date=req.started_at.date().isoformat(),
        **training.stats(series),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That exercise set is already saved") from None
    db.refresh(row)
    return _out(db, row)


@router.post("/api/v2/training/sessions/{session_id}/post", response_model=growth_feed.FeedPostOut, status_code=201)
def post_session(
    session_id: int, req: TrainingPost, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    row = _own(db, uid, session_id)
    if row.social_post_id is not None:
        post = db.query(models.SocialPost).filter(models.SocialPost.id == row.social_post_id).first()
        if post is not None:
            return growth_feed._hydrate_posts(db, [post], uid)[0]
    activity = training.BY_KEY[row.activity_key]
    camera = activity["kind"] == "camera"
    caption = req.caption.strip() or _default_caption(row, activity)
    post = growth_feed.create_feed_post(
        growth_feed.PostCreateIn(
            kind="workout", caption=caption, exercise_key=row.activity_key if camera else None,
            total_reps=row.reps, hold_s=row.duration_s if camera and activity["metric"] == "duration_s" else 0.0,
            distance_m=row.distance_m, duration_s=row.duration_s,
            related_exercise_session_id=row.exercise_session_id,
        ),
        db, token_data,
    )
    row.social_post_id = post.id
    db.commit()
    return post


def _default_caption(row: models.TrainingSession, activity: dict) -> str:
    minutes = max(1, round(row.duration_s / 60))
    if row.distance_m > 0:
        return f"{row.distance_m / 1000:.2f} km {activity['name'].lower()} in {minutes} min on Osiris"
    if row.reps > 0:
        return f"{row.reps} {activity['name'].lower()}s on Osiris"
    return f"{minutes} min of {activity['name'].lower()} on Osiris"


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


@router.get("/api/v2/me/training/summary", response_model=TrainingSummary)
def training_summary(
    activity: str = Query(..., max_length=32), db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    metric = _activity(activity)["metric"]
    rows = db.query(models.TrainingSession).filter(
        models.TrainingSession.user_id == uid, models.TrainingSession.activity_key == activity,
    ).order_by(models.TrainingSession.started_at.asc(), models.TrainingSession.id.asc()).all()
    best = max(rows, key=lambda r: (training.metric_value(r, metric), -r.id), default=None)
    week = _monday(date.today()).isoformat()
    latest = rows[-1] if rows else None
    return TrainingSummary(
        activity_key=activity,
        pr=TrainingRecord(value=training.metric_value(best, metric), unit=training.UNITS[metric], session_id=best.id)
        if best is not None and training.metric_value(best, metric) > 0 else None,
        segments=TrainingSegments(
            workouts=sum(1 for r in rows if r.mode == "train"), challenges=sum(1 for r in rows if r.mode == "challenge")),
        total_duration_s=round(sum(r.duration_s for r in rows), 1),
        total_distance_m=round(sum(r.distance_m for r in rows), 1),
        total_reps=sum(r.reps for r in rows),
        week_sessions=sum(1 for r in rows if r.local_date >= week),
        latest=_out(db, latest, with_series=True) if latest is not None else None,
    )


@router.get("/api/v2/me/training/sessions", response_model=TrainingSessions)
def list_sessions(
    activity: Optional[str] = Query(None, max_length=32),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    q = db.query(models.TrainingSession).filter(models.TrainingSession.user_id == token_data["id"])
    if activity:
        q = q.filter(models.TrainingSession.activity_key == activity)
    rows = q.order_by(models.TrainingSession.started_at.desc(), models.TrainingSession.id.desc()) \
        .offset(offset).limit(limit).all()
    return TrainingSessions(items=[_out(db, r) for r in rows])


@router.get("/api/v2/me/training/sessions/{session_id}", response_model=TrainingSessionOut)
def session_detail(session_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    return _out(db, _own(db, token_data["id"], session_id), with_series=True)


@router.get("/api/v2/me/training/progress", response_model=TrainingProgress)
def training_progress(
    weeks: int = Query(8, ge=1, le=52), db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    starts = [_monday(date.today()) - timedelta(weeks=n) for n in reversed(range(weeks))]
    rows = db.query(models.TrainingSession.local_date, models.TrainingSession.activity_key,
                    models.TrainingSession.duration_s).filter(
        models.TrainingSession.user_id == token_data["id"],
        models.TrainingSession.local_date >= starts[0].isoformat(),
    ).all()
    buckets = {s.isoformat(): TrainingWeek(week_start=s.isoformat(), duration_s=0.0, sessions=0, by_activity={})
               for s in starts}
    for local_date, key, duration in rows:
        week = buckets.get(_monday(date.fromisoformat(local_date)).isoformat())
        if week is None:
            continue
        week.duration_s = round(week.duration_s + duration, 1)
        week.sessions += 1
        week.by_activity[key] = round(week.by_activity.get(key, 0.0) + duration, 1)
    return TrainingProgress(weeks=list(buckets.values()))


@router.get("/api/v2/motivation/quote", response_model=MotivationQuote)
def motivation_quote(exclude: Optional[int] = Query(None), token_data: dict = Depends(get_active_player)):
    return training.quote(exclude)


def connection_cards(db: Session, ids: set[int]) -> dict[int, Connection]:
    profiles = {p.user_id: p for p in db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id.in_(ids or {-1}))}
    out = {}
    for uid in ids:
        p = profiles.get(uid)
        out[uid] = Connection(
            user_id=uid, display_name=p.display_name if p else _display_name(db, uid),
            avatar_url=growth_feed._avatar_for(p) if p else None,
        )
    return out


@router.get("/api/v2/me/connections", response_model=List[Connection])
def my_connections(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    cards = connection_cards(db, training.connection_ids(db, token_data["id"]))
    return sorted(cards.values(), key=lambda c: c.display_name.lower())
