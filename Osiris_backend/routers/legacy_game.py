"""Legacy v1 territory game: domains, vaults, sieges, party roles and the proof preview endpoint."""
import json
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import spatial_utils
from core.clock import _now_naive_utc, _to_naive_utc
from core.rate_limit import _rl_verify
from core.security import get_active_player
from database import get_db
from schemas import (
    ActivityProof,
    DomainCreate,
    DomainResponse,
    DomainSummary,
    PartyRoleResponse,
    SiegeResolveRequest,
    SiegeResolveResponse,
    VaultLockRequest,
    VaultLockResponse,
    VerificationResult,
)
from services import ledger
from services.progression import get_party_role, get_rank, get_title, record_activity
from services.proofs import _consume_proof_or_409, _enforce_proof, _enforce_proof_gps_in_polygon, _run_verification


router = APIRouter()


# --- Economy Constants (Phase 1 MVP — virtual Mana Crystals only) ---
# Real-world currency conversion is deferred to Phase 2.
CLAIM_XP_PER_SQKM = 100           # XP granted per km² on a successful domain claim
SIEGE_WIN_XP_BONUS = 500          # Flat XP bonus for winning a siege

# Payout splits on siege WIN (paid tier): pot = defender_vault + challenger_match
WAR_TAX_PCT = 0.20                # Platform's cut from a winning pot (80/20 to challenger/system)

# Payout splits on siege LOSS (paid tier): challenger's forfeited match is split
LOSS_DEFENDER_PCT = 0.50          # Goes back into defender's Vault (grows the moat)
LOSS_SYSTEM_PCT = 0.30            # Platform retains outright
LOSS_DISCOUNT_PCT = 0.20          # Banked as a retry discount for the same challenger vs. same domain

def calculate_claim_xp(area_sqkm: float) -> int:
    """XP awarded for claiming land. Floors to keep small traces from earning fractional XP."""
    return int(area_sqkm * CLAIM_XP_PER_SQKM)


@router.get("/api/v1/domains/nearby", response_model=List[DomainSummary])
def get_nearby_domains(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Returns existing claimed domains whose centroid falls within `radius_km` of (lat, lng),
    sorted nearest-first.

    This endpoint is AUTHENTICATED (a player JWT is required). Previously it
    was public, which leaked `owner_id` + exact polygon geometry + `vault_balance` for any
    lat/lng to any unauthenticated caller — a stalking + economic-recon primitive. Requiring
    auth closes the unauthenticated leak. NOTE (residual risk, see register): the response
    still exposes raw `owner_id` and full geometry to *authenticated* players; coarsening to an
    opaque handle + centroid-only for non-owners is a follow-up that changes the client
    contract and is deferred for a product decision. MVP uses an in-memory haversine sweep;
    PostGIS `ST_DWithin` replaces this in Phase 4."""
    candidates = db.query(models.Domain).all()
    out: List[DomainSummary] = []
    for d in candidates:
        if not d.geometry_json:
            continue
        try:
            coords = json.loads(d.geometry_json)
        except Exception:
            continue
        if not coords:
            continue
        # Centroid as the simple average of vertex coords. Fine for park-sized polygons;
        # PostGIS `ST_Centroid` will be exact in Phase 2.
        c_lat = sum(c["lat"] for c in coords) / len(coords)
        c_lng = sum(c["lng"] for c in coords) / len(coords)
        dist = spatial_utils.haversine_distance(lat, lng, c_lat, c_lng)
        if dist > radius_km:
            continue
        out.append(DomainSummary(
            id=d.id,
            owner_id=d.owner_id,
            area_sqkm=d.area_sqkm or 0.0,
            defense_score=d.defense_score or 0,
            defense_type=d.defense_type or "pushups",
            vault_balance=d.vault_balance or 0,
            is_protected=(d.vault_balance or 0) > 0,
            geometry=coords,
            centroid_lat=c_lat,
            centroid_lng=c_lng,
            distance_km=round(dist, 4),
        ))
    out.sort(key=lambda x: x.distance_km)
    return out


@router.post("/api/v1/domains", response_model=DomainResponse)
def submit_domain(domain_req: DomainCreate, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Processes a completed Domain Trace, validates anti-cheat, and claims the territory."""

    if token_data["id"] != domain_req.owner_id:
        raise HTTPException(status_code=403, detail="Not authorized to act as this user")

    # 0. Verify the user exists
    user = db.query(models.User).filter(models.User.id == domain_req.owner_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # 0.5. ML Referee: if a proof is attached, validate it and override defense_score with the
    # verified value. Without a proof we fall back to client-trusted defense_score (legacy).
    verification = _enforce_proof(domain_req.defense_proof, expected_activity_type=domain_req.defense_type)
    if verification is not None:
        domain_req.defense_score = verification.verified_score
    # 0.55. Co-location: if the proof carries GPS samples, they must land inside the polygon
    # the user is trying to claim. Cheapest big anti-cheat win — without this a verified
    # workout from anywhere can be attached to any polygon.
    claim_polygon = [{"lat": c.lat, "lng": c.lng} for c in domain_req.coordinates]
    _enforce_proof_gps_in_polygon(domain_req.defense_proof, claim_polygon, context="domain_claim")
    # 0.6. Replay-attack guard: every proof can be consumed exactly once across the system.
    _consume_proof_or_409(db, user.id, domain_req.defense_proof, source="domain_claim")

    # 1. Anti-Cheat: Validate Closure Tolerance
    # The user must return to their starting point to close the polygon (within 20 meters)
    start_coord = domain_req.coordinates[0]
    end_coord = domain_req.coordinates[-1]
    closure_dist = spatial_utils.haversine_distance(
        start_coord.lat, start_coord.lng, end_coord.lat, end_coord.lng
    )
    if closure_dist > 0.02: # 0.02 km = 20 meters
        raise HTTPException(status_code=400, detail="Domain Closure Failed: Loop not closed within 20m.")

    # 2. Anti-Cheat: Velocity Lock
    # Ensure the user didn't jump in a car to draw a massive shape
    if spatial_utils.check_velocity_violation(domain_req.coordinates, max_speed_kmh=25.0):
        raise HTTPException(status_code=400, detail="Velocity Lock triggered. Trace Shattered.")

    # 3. Calculate the Area in square kilometers
    area = spatial_utils.calculate_polygon_area_sqkm(domain_req.coordinates)
    if area < 0.001:
        raise HTTPException(status_code=400, detail="Domain too small.")

    # 4. Save Domain to the Database
    geom_json = json.dumps([{"lat": c.lat, "lng": c.lng} for c in domain_req.coordinates])

    new_domain = models.Domain(
        owner_id=user.id,
        geometry_json=geom_json,
        area_sqkm=round(area, 4),
        defense_score=domain_req.defense_score,
        defense_type=domain_req.defense_type
    )

    # 4.5 Siege Logic: Check if this new domain swallows any existing domains
    all_domains = db.query(models.Domain).filter(models.Domain.owner_id != user.id).all()
    sieges_created = 0
    for existing_domain in all_domains:
        if existing_domain.geometry_json:
            try:
                target_coords = json.loads(existing_domain.geometry_json)
                if spatial_utils.is_polygon_swallowed(target_coords, domain_req.coordinates):
                    # Trigger a Siege! Snapshot the defender's score so it can't be edited before resolution.
                    new_siege = models.SiegeLog(
                        challenger_id=user.id,
                        target_domain_id=existing_domain.id,
                        status="pending_feat",
                        defender_score_snapshot=existing_domain.defense_score or 0
                    )
                    db.add(new_siege)
                    sieges_created += 1
            except Exception:
                pass # Skip if JSON parsing fails

    # 5. Add the land to the user's cumulative total and upgrade their Title if necessary
    user.cumulative_area += round(area, 4)
    user.title = get_title(user.cumulative_area)

    # 6. Award claim XP, increment the matching Party Stat, and re-evaluate Rank
    xp_gained = calculate_claim_xp(area)
    user.xp += xp_gained
    user.last_activity_date = _to_naive_utc(domain_req.device_timestamp)
    user.rank = get_rank(user.xp, user.last_activity_date)

    # 7. Append to ActivityLog so the 30-day rolling Party Stats window can include this rep.
    db.add(new_domain)
    db.flush()  # need new_domain.id for the activity log's related_id
    record_activity(
        db,
        user,
        activity_type=domain_req.defense_type,
        score=domain_req.defense_score,
        occurred_at=_to_naive_utc(domain_req.device_timestamp),
        source="domain_claim",
        related_id=new_domain.id,
        verified=bool(verification and verification.verified),
        confidence=verification.confidence if verification else 1.0,
        proof=domain_req.defense_proof,
    )

    db.commit()
    db.refresh(new_domain)

    return DomainResponse(
        id=new_domain.id,
        area_sqkm=new_domain.area_sqkm,
        defense_score=new_domain.defense_score,
        message=f"Domain secured! You claimed {round(area, 4)} km² and are now a {user.title}.",
        sieges_triggered=sieges_created,
        xp_awarded=xp_gained
    )

@router.post("/api/v1/domains/{domain_id}/vault", response_model=VaultLockResponse)
def lock_vault(domain_id: int, req: VaultLockRequest, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Lock (or top up) an Ownership Fee on a domain. Crystals are deducted from the owner's
    wallet and added to the domain's Vault. Vault balance doubles as the required Challenger
    Match amount. Topping up is allowed; unlocking (lowering) is deferred to Phase 2."""

    if token_data["id"] != req.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to act as this user")

    domain = db.query(models.Domain).filter(models.Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found.")

    # Only the owner can protect their domain
    if domain.owner_id != req.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can lock this domain's Vault.")

    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Target vault balance must be a top-up, not a withdrawal
    delta = req.amount - (domain.vault_balance or 0)
    if delta <= 0:
        raise HTTPException(status_code=400, detail="New vault amount must exceed current vault balance.")

    if user.mana_crystals < delta:
        raise HTTPException(status_code=402, detail="Insufficient Mana Crystals.")

    ledger.apply_crystal_delta(
        db, user, -delta, "vault_lock",
        related_domain_id=domain.id,
        note=f"Vault lock to {req.amount} on domain {domain.id}",
    )
    domain.vault_balance = req.amount
    db.commit()
    db.refresh(domain)
    db.refresh(user)

    return VaultLockResponse(
        domain_id=domain.id,
        vault_balance=domain.vault_balance,
        crystals_spent=delta,
        mana_crystals_remaining=user.mana_crystals,
        message=f"Domain protected. {delta} crystals locked into the Vault."
    )


@router.post("/api/v1/sieges/{siege_id}/resolve", response_model=SiegeResolveResponse)
def resolve_siege(siege_id: int, req: SiegeResolveRequest, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """Resolve a pending siege. Challenger submits their Defense Feat score.
    WIN: defender's polygon erased, pot (defender vault + challenger match) paid 80/20 to
         challenger/system.
    LOSS: challenger's match is split 50% to defender vault / 30% to system / 20% banked as a
          retry-discount against the same target_domain_id for this challenger.
    Any unconsumed retry discount for this challenger+domain pair is auto-applied to reduce
    the challenger's out-of-pocket match on this attempt."""

    siege = db.query(models.SiegeLog).filter(models.SiegeLog.id == siege_id).first()
    if not siege:
        raise HTTPException(status_code=404, detail="Siege not found.")
    if siege.status != "pending_feat":
        raise HTTPException(status_code=400, detail=f"Siege already resolved (status={siege.status}).")

    if token_data["id"] != siege.challenger_id:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this siege")

    challenger = db.query(models.User).filter(models.User.id == siege.challenger_id).first()
    target_domain = db.query(models.Domain).filter(models.Domain.id == siege.target_domain_id).first()
    if not challenger or not target_domain:
        raise HTTPException(status_code=404, detail="Challenger or target domain missing.")

    defender = db.query(models.User).filter(models.User.id == target_domain.owner_id).first()
    device_ts = _to_naive_utc(req.device_timestamp)

    # Capture defense_type BEFORE any potential db.delete(target_domain) on win path.
    target_defense_type = target_domain.defense_type or "pushups"

    # ML Referee: if the challenger attached a proof, it must match the defender's exercise
    # and pass verification. Verified score overrides the client-supplied challenger_score.
    verification = _enforce_proof(req.challenger_proof, expected_activity_type=target_defense_type)
    if verification is not None:
        req.challenger_score = verification.verified_score
    # Co-location: the challenger's GPS samples (if present) must land inside the polygon
    # being sieged — you can't take someone's land from another time zone.
    if req.challenger_proof is not None and target_domain.geometry_json:
        try:
            target_polygon = json.loads(target_domain.geometry_json)
            _enforce_proof_gps_in_polygon(req.challenger_proof, target_polygon, context="siege_resolve")
        except (ValueError, json.JSONDecodeError):
            # Corrupted polygon JSON — skip the check rather than block the resolve.
            pass
    # Replay-attack guard
    _consume_proof_or_409(db, challenger.id, req.challenger_proof, source="siege_resolve")

    required_match = target_domain.vault_balance or 0

    # Look up any available retry discount from a previous failed attempt at THIS domain.
    discount_row = (
        db.query(models.SiegeDiscount)
        .filter(
            models.SiegeDiscount.challenger_id == challenger.id,
            models.SiegeDiscount.target_domain_id == target_domain.id,
            models.SiegeDiscount.consumed == 0,
        )
        .first()
    )
    discount_applied = 0
    if discount_row and required_match > 0:
        discount_applied = min(discount_row.amount or 0, required_match)

    out_of_pocket = max(0, required_match - discount_applied)

    # Paid tier: challenger must cover the out-of-pocket portion of the match.
    if out_of_pocket > 0 and challenger.mana_crystals < out_of_pocket:
        raise HTTPException(status_code=402, detail="Insufficient Mana Crystals to match defender's Vault.")

    # Consume the discount up front — whether they win or lose, it's been applied.
    if discount_row and discount_applied > 0:
        discount_row.consumed = 1
        discount_row.consumed_at = device_ts

    defender_score = siege.defender_score_snapshot or 0
    is_time_trial = target_defense_type in ("run", "walk", "sprint")
    if is_time_trial:
        # Time trials are won by a LOWER time. A free-tier domain has no baseline
        # (defender_score == 0): there is no real time to beat, so any positive challenger
        # time wins (§3.1 fix — previously `score <= 0 and score > 0` was always False,
        # making free-tier time-trial domains unconquerable). Paid/seeded tiers keep the
        # genuine "beat the baseline" comparison.
        if defender_score == 0:
            challenger_won = req.challenger_score > 0
        else:
            challenger_won = 0 < req.challenger_score <= defender_score
    else:
        challenger_won = req.challenger_score > defender_score

    crystals_awarded = 0
    new_discount_banked = 0
    xp_gained = 0

    if challenger_won:
        # Debit only the out-of-pocket; the discount portion was subsidized by the system.
        if required_match > 0:
            # NB: target_domain is db.delete()'d below on the win path, so we deliberately
            # do NOT set related_domain_id here (it would dangle); the id lives in the note.
            if out_of_pocket > 0:
                ledger.apply_crystal_delta(
                    db, challenger, -out_of_pocket, "siege_out_of_pocket",
                    related_siege_id=siege.id,
                    note=f"Match staked on siege {siege.id} win (domain {target_domain.id})",
                )
            pot = required_match * 2  # treat as full match vs defender vault
            winner_share = int(pot * (1 - WAR_TAX_PCT))  # 80%
            war_tax_revenue = pot - winner_share          # 20% to platform
            ledger.apply_crystal_delta(
                db, challenger, winner_share, "siege_win_payout",
                related_siege_id=siege.id,
                note=f"80% pot payout on siege {siege.id} win (domain {target_domain.id})",
            )
            crystals_awarded = winner_share
            target_domain.vault_balance = 0
            # Ledger: record platform's War Tax cut.
            if war_tax_revenue > 0:
                db.add(models.PlatformRevenue(
                    source="siege_war_tax",
                    amount=war_tax_revenue,
                    user_id=challenger.id,
                    related_siege_id=siege.id,
                    note=f"20% of pot {pot} on siege win",
                ))

        # Transfer land: defender loses area; challenger's cumulative_area was bumped on claim.
        if defender:
            defender.cumulative_area = max(0.0, defender.cumulative_area - (target_domain.area_sqkm or 0.0))
            defender.title = get_title(defender.cumulative_area)

        # Remove defender's polygon entirely.
        db.delete(target_domain)

        # Reward challenger XP + rank bump.
        xp_gained = SIEGE_WIN_XP_BONUS
        challenger.xp += xp_gained
        challenger.last_activity_date = device_ts
        challenger.rank = get_rank(challenger.xp, challenger.last_activity_date)

        siege.status = "won"
        msg_parts = ["Siege won. Claimed defender's territory"]
        if required_match > 0:
            msg_parts.append(f" and {crystals_awarded} crystals")
        if discount_applied > 0:
            msg_parts.append(f" (retry discount of {discount_applied} applied)")
        message = "".join(msg_parts) + "."
    else:
        # LOSS: challenger forfeits their match, split 50/30/20.
        if required_match > 0:
            if out_of_pocket > 0:
                ledger.apply_crystal_delta(
                    db, challenger, -out_of_pocket, "siege_forfeit",
                    related_siege_id=siege.id, related_domain_id=target_domain.id,
                    note=f"Forfeited match on siege {siege.id} loss",
                )
            defender_cut = int(required_match * LOSS_DEFENDER_PCT)
            system_keep = int(required_match * LOSS_SYSTEM_PCT)         # 30% — platform revenue
            future_discount_cut = int(required_match * LOSS_DISCOUNT_PCT)

            if defender_cut > 0:
                target_domain.vault_balance += defender_cut  # defender's moat grows
            if future_discount_cut > 0:
                new_discount = models.SiegeDiscount(
                    challenger_id=challenger.id,
                    target_domain_id=target_domain.id,
                    amount=future_discount_cut,
                    consumed=0,
                )
                db.add(new_discount)
                new_discount_banked = future_discount_cut
            # Ledger: record platform's loss-side keep.
            if system_keep > 0:
                db.add(models.PlatformRevenue(
                    source="siege_loss_keep",
                    amount=system_keep,
                    user_id=challenger.id,
                    related_siege_id=siege.id,
                    note=f"30% of forfeit {required_match} on siege loss",
                ))
        siege.status = "failed"
        message = "Defense held. Your Defense Feat did not beat the defender's Ghost score."
        if new_discount_banked > 0:
            message += f" {new_discount_banked} crystals banked as a retry discount."

    # Stat increment + ActivityLog: runs regardless of outcome — the challenger performed
    # the activity. related_id points at the siege itself for traceability.
    record_activity(
        db,
        challenger,
        activity_type=target_defense_type,
        score=req.challenger_score,
        occurred_at=device_ts,
        source="siege_resolve",
        related_id=siege.id,
        verified=bool(verification and verification.verified),
        confidence=verification.confidence if verification else 1.0,
        proof=req.challenger_proof,
    )

    siege.challenger_fee = out_of_pocket
    siege.challenger_score = req.challenger_score
    siege.resolved_at = device_ts

    db.commit()

    return SiegeResolveResponse(
        siege_id=siege.id,
        status=siege.status,
        defender_score=defender_score,
        challenger_score=req.challenger_score,
        crystals_awarded=crystals_awarded,
        xp_awarded=xp_gained,
        discount_applied=discount_applied,
        new_discount_banked=new_discount_banked,
        message=message
    )


@router.get("/api/v1/users/{user_id}/party-role", response_model=PartyRoleResponse)
def get_user_party_role(
    user_id: int,
    window_days: Optional[int] = None,
    db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    if token_data["id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this user's role")
    """Returns the user's Party Role. Two modes:
       - default (no `window_days`)  → lifetime totals on `User.{str/agi/end/con}_stat`
       - `?window_days=N`            → rolling sum of `ActivityLog.score` per stat over the
                                       last N days, computed from `occurred_at`.

    Phase 1 wrote stats only as lifetime totals; v2.7 adds the ActivityLog-backed rolling
    path so the 30-day Party Role can flip even if a user's career totals stay unchanged."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if window_days is None or window_days <= 0:
        role, leading_stat = get_party_role(user)
        return PartyRoleResponse(
            user_id=user.id,
            role=role,
            str_stat=user.str_stat or 0,
            agi_stat=user.agi_stat or 0,
            end_stat=user.end_stat or 0,
            con_stat=user.con_stat or 0,
            leading_stat=leading_stat,
        )

    # Rolling-window path: aggregate ActivityLog rows for this user since (now - window_days).
    cutoff = _now_naive_utc() - timedelta(days=window_days)
    rows = (
        db.query(models.ActivityLog)
        .filter(
            models.ActivityLog.user_id == user.id,
            models.ActivityLog.occurred_at >= cutoff,
            models.ActivityLog.stat_column.isnot(None),
        )
        .all()
    )
    totals = {"str_stat": 0, "agi_stat": 0, "end_stat": 0, "con_stat": 0}
    for r in rows:
        if r.stat_column in totals:
            totals[r.stat_column] += r.score or 0

    # Reuse get_party_role's tie-break order by mocking a temp object with the windowed totals.
    class _Tmp:
        pass
    tmp = _Tmp()
    for k, v in totals.items():
        setattr(tmp, k, v)
    role, leading_stat = get_party_role(tmp)  # type: ignore[arg-type]
    return PartyRoleResponse(
        user_id=user.id,
        role=role,
        str_stat=totals["str_stat"],
        agi_stat=totals["agi_stat"],
        end_stat=totals["end_stat"],
        con_stat=totals["con_stat"],
        leading_stat=leading_stat,
    )


@router.post("/api/v1/activities/verify", response_model=VerificationResult)
def verify_activity_endpoint(proof: ActivityProof, _rl: None = Depends(_rl_verify)):
    """Stateless preview of the ML Referee. The frontend can call this to confirm a workout
    will pass before submitting the real action (claim, siege, bounty). No DB writes.
    Note: the co-location check is NOT applied here — that requires the target polygon /
    geofence which only the calling endpoint knows."""
    return _run_verification(proof)
