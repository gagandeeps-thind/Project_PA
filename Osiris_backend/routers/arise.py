# ruff: noqa: B008  (FastAPI dependencies are declared as argument defaults)
"""Arise tab: public routes (and, in later phases, domains, attacks and heatmaps)."""
import json
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import models
import spatial_utils
from core.security import get_active_player
from database import get_db
from growth_social import _display_name
from routers.challenges import register_course
from routers.runs import _get_player_run
from schemas import AriseRoute, AriseRoutePublish, CourseCreate
from services import arise
from services.challenge_store import _run_points

router = APIRouter()

KM_PER_DEG_LAT = 111.195


def _route(db: Session, course: models.Course) -> AriseRoute:
    return AriseRoute(
        id=course.id, name=course.name, activity_type=course.activity_type, distance_m=course.distance_m,
        benchmark_seconds=course.benchmark_seconds, hide_ends=course.hide_ends,
        owner_name=_display_name(db, course.owner_id), line=json.loads(course.public_route_json or "[]"),
    )


@router.post("/api/v2/arise/routes", response_model=AriseRoute, status_code=201)
def publish_route(req: AriseRoutePublish, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Publish an accepted run as a route every player can see and run. Registers the course (same rules
    and privacy trim as /api/v2/courses), then makes it public. Publishing the same run again returns it."""
    run = _get_player_run(db, req.run_session_id, token_data["id"])
    summary = register_course(CourseCreate(run_id=run.id, name=req.name), db, token_data)
    course = db.query(models.Course).filter(models.Course.id == summary.id).one()
    full = [(p[0], p[1]) for p in _run_points(db, run.id)]
    trimmed = [(p[0], p[1]) for p in json.loads(course.route_json)]
    course.activity_type = run.activity_type or "run"
    course.hide_ends = req.hide_ends
    course.is_public = True
    course.public_route_json = json.dumps(arise.public_line(full, trimmed, req.hide_ends), separators=(",", ":"))
    db.commit()
    return _route(db, course)


@router.get("/api/v2/arise/routes", response_model=List[AriseRoute])
def nearby_routes(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10.0, gt=0, le=50),
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Public routes whose marker is within `radius_km`, nearest first (at most 100)."""
    span = radius_km / KM_PER_DEG_LAT
    rows = db.query(models.Course).filter(
        models.Course.is_public.is_(True),
        models.Course.status == "active",
        models.Course.public_lat.between(lat - span, lat + span),
    ).all()
    near = sorted(
        ((spatial_utils.haversine_distance(lat, lng, c.public_lat, c.public_lng), c) for c in rows),
        key=lambda pair: pair[0],
    )
    near = [pair for pair in near if pair[0] <= radius_km][:100]
    return [_route(db, c) for _, c in near]
