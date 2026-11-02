# ruff: noqa: B008  (FastAPI dependencies are declared as argument defaults)
"""Group challenges on the Start tab: friends (connections) race towards a shared goal of one
activity, and admins publish official Osiris challenges open to everyone.

Progress counts only sessions started from the Challenge page (`mode=challenge`). Challenges
never touch crystals."""
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import growth_feed
import models
from core.clock import _now_naive_utc
from core.security import get_active_player, get_current_admin
from database import get_db
from routers.training import connection_cards
from schemas import (
    GroupChallengeCreate,
    GroupChallengeLists,
    GroupChallengeOut,
    GroupMemberOut,
)
from services import player_safety, training

router = APIRouter()

TOP = 3
MINE_LIMIT = 30


def _status(ch: models.GroupChallenge) -> str:
    if ch.status == "cancelled":
        return "cancelled"
    return "ended" if _now_naive_utc() >= ch.ends_at else "active"


def _validate(req: GroupChallengeCreate) -> None:
    activity = training.BY_KEY.get(req.activity_key)
    if activity is None:
        raise HTTPException(status_code=422, detail="Unknown activity")
    if req.metric in ("distance_m", "reps") and activity["metric"] != req.metric:
        raise HTTPException(status_code=422, detail="That goal does not fit the activity")


def _new(req: GroupChallengeCreate, creator_id: Optional[int], official: bool) -> models.GroupChallenge:
    now = _now_naive_utc()
    return models.GroupChallenge(
        creator_id=creator_id, is_official=official, title=req.title.strip(), activity_key=req.activity_key,
        metric=req.metric, target=req.target, starts_at=now, ends_at=now + timedelta(days=req.days), status="active",
    )


def _memberships(db: Session, uid: int) -> dict[int, str]:
    return dict(db.query(models.GroupChallengeMember.challenge_id, models.GroupChallengeMember.status)
                .filter(models.GroupChallengeMember.user_id == uid).all())


def _visible(db: Session, ch: models.GroupChallenge, uid: int, mine: dict[int, str]) -> bool:
    return (ch.is_official or ch.id in mine or ch.creator_id == uid
            or (ch.creator_id is not None and ch.creator_id in training.connection_ids(db, uid)))


def _cards(db: Session, uid: int, challenges: list[models.GroupChallenge], mine: dict[int, str],
           full: bool = False) -> list[GroupChallengeOut]:
    progress = training.group_progress(db, challenges)
    blocked = player_safety.blocked_user_ids(db, uid) if uid > 0 else set()
    people = connection_cards(db, {u for p in progress.values() for u in p if u not in blocked})
    out: list[GroupChallengeOut] = []
    for ch in challenges:
        board = sorted(
            ((u, v) for u, v in progress.get(ch.id, {}).items() if u not in blocked),
            key=lambda kv: (-kv[1], kv[0]),
        )
        members = [GroupMemberOut(**people[u].model_dump(), progress=v) for u, v in board if u in people]
        fields = dict(
            id=ch.id, title=ch.title, activity_key=ch.activity_key, metric=ch.metric, target=ch.target,
            starts_at=ch.starts_at, ends_at=ch.ends_at, is_official=ch.is_official, creator_id=ch.creator_id,
            created_by_me=ch.creator_id is not None and ch.creator_id == uid,
            status=_status(ch), my_status=mine.get(ch.id), my_progress=progress.get(ch.id, {}).get(uid, 0.0),
            members=len(members), top=members[:TOP],
        )
        out.append(GroupChallengeOut(**fields, leaderboard=members if full else []))
    return out


def _load(db: Session, uid: int, challenge_id: int) -> tuple[models.GroupChallenge, dict[int, str]]:
    ch = db.query(models.GroupChallenge).filter(models.GroupChallenge.id == challenge_id).first()
    mine = _memberships(db, uid)
    if ch is None or not _visible(db, ch, uid, mine):
        raise HTTPException(status_code=404, detail="Challenge not found")
    return ch, mine


def _detail(db: Session, uid: int, ch: models.GroupChallenge) -> GroupChallengeOut:
    return _cards(db, uid, [ch], _memberships(db, uid), full=True)[0]


@router.get("/api/v2/group-challenges", response_model=GroupChallengeLists)
def list_group_challenges(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    now = _now_naive_utc()
    mine = _memberships(db, uid)
    active = [models.GroupChallenge.status == "active", models.GroupChallenge.ends_at > now]
    official = db.query(models.GroupChallenge).filter(models.GroupChallenge.is_official.is_(True), *active) \
        .order_by(models.GroupChallenge.ends_at.asc()).all()
    joined = db.query(models.GroupChallenge).filter(
        models.GroupChallenge.id.in_([cid for cid, s in mine.items() if s == "joined"] or [-1]),
        models.GroupChallenge.is_official.is_(False), models.GroupChallenge.status == "active",
    ).order_by(models.GroupChallenge.ends_at.desc()).limit(MINE_LIMIT).all()
    invited = db.query(models.GroupChallenge).filter(
        models.GroupChallenge.id.in_([cid for cid, s in mine.items() if s == "invited"] or [-1]), *active,
    ).order_by(models.GroupChallenge.ends_at.asc()).all()
    friends = training.connection_ids(db, uid)
    open_to_me = db.query(models.GroupChallenge).filter(
        models.GroupChallenge.creator_id.in_(friends or {-1}), models.GroupChallenge.is_official.is_(False),
        models.GroupChallenge.id.notin_(list(mine) or [-1]), *active,
    ).order_by(models.GroupChallenge.ends_at.asc()).all()
    return GroupChallengeLists(
        official=_cards(db, uid, official, mine), mine=_cards(db, uid, joined, mine),
        invited=_cards(db, uid, invited, mine), connections=_cards(db, uid, open_to_me, mine),
    )


@router.post("/api/v2/group-challenges", response_model=GroupChallengeOut, status_code=201)
def create_group_challenge(
    req: GroupChallengeCreate, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player),
):
    uid = token_data["id"]
    _validate(req)
    invitees = set(req.invitee_ids) - {uid}
    if not invitees <= training.connection_ids(db, uid):
        raise HTTPException(status_code=422, detail="You can only invite your connections")
    ch = _new(req, uid, official=False)
    db.add(ch)
    db.flush()
    db.add(models.GroupChallengeMember(challenge_id=ch.id, user_id=uid, status="joined", joined_at=ch.starts_at))
    host = connection_cards(db, {uid})[uid].display_name
    for friend in invitees:
        db.add(models.GroupChallengeMember(challenge_id=ch.id, user_id=friend, status="invited", invited_by=uid))
        growth_feed.create_notification(
            db, friend, "group_challenge_invite", "Group challenge invite",
            f"{host} invited you to {ch.title}", action_route=f"group/{ch.id}",
        )
    db.commit()
    return _detail(db, uid, ch)


@router.get("/api/v2/group-challenges/{challenge_id}", response_model=GroupChallengeOut)
def group_challenge_detail(challenge_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    ch, _ = _load(db, token_data["id"], challenge_id)
    return _detail(db, token_data["id"], ch)


@router.post("/api/v2/group-challenges/{challenge_id}/join", response_model=GroupChallengeOut)
def join_group_challenge(challenge_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    ch, _ = _load(db, uid, challenge_id)
    if _status(ch) != "active":
        raise HTTPException(status_code=409, detail="This challenge is over")
    row = db.query(models.GroupChallengeMember).filter(
        models.GroupChallengeMember.challenge_id == ch.id, models.GroupChallengeMember.user_id == uid).first()
    if row is None:
        row = models.GroupChallengeMember(challenge_id=ch.id, user_id=uid)
        db.add(row)
    if row.status != "joined":
        row.status, row.joined_at = "joined", _now_naive_utc()
    db.commit()
    return _detail(db, uid, ch)


@router.post("/api/v2/group-challenges/{challenge_id}/leave", response_model=GroupChallengeOut)
def leave_group_challenge(challenge_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    ch, _ = _load(db, uid, challenge_id)
    if ch.creator_id == uid:
        raise HTTPException(status_code=409, detail="The creator cancels the challenge instead")
    db.query(models.GroupChallengeMember).filter(
        models.GroupChallengeMember.challenge_id == ch.id, models.GroupChallengeMember.user_id == uid,
    ).delete(synchronize_session=False)
    db.commit()
    return _detail(db, uid, ch)


@router.post("/api/v2/group-challenges/{challenge_id}/cancel", response_model=GroupChallengeOut)
def cancel_group_challenge(challenge_id: int, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    ch, _ = _load(db, uid, challenge_id)
    if ch.creator_id != uid:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    ch.status = "cancelled"
    db.commit()
    return _detail(db, uid, ch)


@router.post("/api/v2/admin/group-challenges", response_model=GroupChallengeOut, status_code=201)
def create_official_challenge(
    req: GroupChallengeCreate, db: Session = Depends(get_db), token_data: dict = Depends(get_current_admin),
):
    _validate(req)
    ch = _new(req, None, official=True)
    db.add(ch)
    db.commit()
    return _cards(db, -1, [ch], {}, full=True)[0]


@router.get("/api/v2/admin/group-challenges", response_model=List[GroupChallengeOut])
def list_official_challenges(db: Session = Depends(get_db), token_data: dict = Depends(get_current_admin)):
    rows = db.query(models.GroupChallenge).filter(models.GroupChallenge.is_official.is_(True)) \
        .order_by(models.GroupChallenge.created_at.desc()).limit(200).all()
    return _cards(db, -1, rows, {})
