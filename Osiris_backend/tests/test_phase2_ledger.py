"""Money-path tests: player-side Crystal Ledger + the
free-tier time-trial conquest bug.

No pytest dependency — run directly:

    cd Osiris_backend
    OSIRIS_ENV=test python tests/test_phase2_ledger.py

Style mirrors tests/test_phase2_security.py: a module-level `_check(name, cond)` helper,
env set at the top, an isolated in-memory DB, and a `__main__` block that prints PASS/FAIL
and exits non-zero on any failure.

Coverage:
  - Ledger conservation: after a bounty reward, a vault lock, and a siege resolve,
    sum(CrystalLedger.delta for the user) == user.mana_crystals.
  - The ledger is the only write path: every money mutation writes exactly one (or, on a
    siege win, two) CrystalLedger row(s) with the right reason_code and a balance_after
    that equals the running wallet.
  - §3.1: a free-tier (vault_balance=0, defense_type='run') domain CAN now be conquered by
    a positive time-trial score. This case FAILS on the pre-fix code (the old
    `score <= 0 and score > 0` was always False) and PASSES after the fix.
  - Reconciliation `check()` passes for every user after the operations above.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND)

# Fail-closed boot check requires an explicit dev/test env.
os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "phase2-ledger-test-secret-aaaaaaaaaaaaaaaa")

from datetime import datetime, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from database import Base  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402
from main import app, get_db, get_password_hash, get_rank, get_title  # noqa: E402
from services import ledger  # noqa: E402

_FAILURES = []


def _check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {name}")
    if not cond:
        _FAILURES.append(name)


# --- Isolated in-memory DB shared by the FastAPI app and the test ---------------------------
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
Base.metadata.create_all(bind=engine)

# Load the reconciliation script as a module (scripts/ is not a package).
_recon_spec = importlib.util.spec_from_file_location(
    "reconcile_ledger", os.path.join(BACKEND, "scripts", "reconcile_ledger.py")
)
reconcile = importlib.util.module_from_spec(_recon_spec)
_recon_spec.loader.exec_module(reconcile)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _now_str() -> str:
    return "2026-06-29T12:00:00Z"


def _auth(uid: int) -> dict:
    tok = main.create_access_token({"sub": str(uid), "role": "player"})
    return {"Authorization": f"Bearer {tok}"}


def _ledger_rows(db, uid):
    return (
        db.query(models.CrystalLedger)
        .filter(models.CrystalLedger.user_id == uid)
        .order_by(models.CrystalLedger.id)
        .all()
    )


def _ledger_sum(db, uid) -> int:
    return (
        db.query(func.coalesce(func.sum(models.CrystalLedger.delta), 0))
        .filter(models.CrystalLedger.user_id == uid)
        .scalar()
    )


def _make_user_direct(db, email, crystals=0):
    """Create a helper user (e.g. a defender) directly, keeping the ledger invariant by
    routing the opening balance through the service."""
    u = models.User(
        email=email, hashed_password=get_password_hash("pw"),
        bmi=22.0, avatar_class="Tank", xp=0, rank=get_rank(0), title=get_title(0.0),
        cumulative_area=1.0, last_activity_date=_now(), streak=0, mana_crystals=0,
    )
    db.add(u)
    db.flush()
    if crystals:
        ledger.apply_crystal_delta(db, u, crystals, "opening_balance", note="test helper")
    db.commit()
    db.refresh(u)
    return u


def _onboard(email):
    r = client.post("/api/v1/onboard", json={
        "email": email, "password": "PlayerTest1!",
        "weight_kg": 75, "height_m": 1.8, "preferred_path": "Strength",
        "device_timestamp": _now_str(),
    })
    assert r.status_code == 200, f"onboard failed: {r.status_code} {r.text}"
    db = TestingSessionLocal()
    try:
        u = db.query(models.User).filter(models.User.email == email).first()
        return u.id
    finally:
        db.close()


# --- Test 1: opening balance row written at registration ------------------------------------
def test_opening_balance_row():
    uid = _onboard("ledger_open@test.com")
    db = TestingSessionLocal()
    try:
        u = db.get(models.User, uid)
        rows = _ledger_rows(db, uid)
        _check("opening grant equals OPENING_CRYSTAL_BALANCE",
               u.mana_crystals == models.OPENING_CRYSTAL_BALANCE)
        _check("exactly one ledger row at registration", len(rows) == 1)
        _check("opening row reason_code + balance_after correct",
               rows[0].reason_code == "opening_balance"
               and rows[0].delta == models.OPENING_CRYSTAL_BALANCE
               and rows[0].balance_after == models.OPENING_CRYSTAL_BALANCE)
        _check("opening conservation sum(deltas)==mana_crystals",
               _ledger_sum(db, uid) == u.mana_crystals)
    finally:
        db.close()


# --- Test 2: bounty reward + vault lock + siege win each journal correctly -------------------
def test_full_money_path_conservation():
    uid = _onboard("ledger_flow@test.com")

    # --- bounty reward (+crystals) ---
    db = TestingSessionLocal()
    bounty = models.Bounty(
        title="Visit Park", description="proximity only", bounty_type="daily",
        target_lat=44.6, target_lng=-63.6, radius_m=100.0,
        activity_type="walk", target_score=0, xp_reward=10, crystal_reward=50,
        max_completions=50, completions_count=0, is_active=1,
    )
    db.add(bounty)
    db.commit()
    bounty_id = bounty.id
    db.close()

    r = client.post(f"/api/v1/bounties/{bounty_id}/complete", headers=_auth(uid), json={
        "user_id": uid, "user_lat": 44.6, "user_lng": -63.6, "score": 0,
        "device_timestamp": _now_str(),
    })
    _check("bounty complete -> 200", r.status_code == 200)

    db = TestingSessionLocal()
    rows = _ledger_rows(db, uid)
    br = [x for x in rows if x.reason_code == "bounty_reward"]
    _check("bounty_reward row written with delta +50",
           len(br) == 1 and br[0].delta == 50 and br[0].related_bounty_id == bounty_id)
    _check("bounty_reward balance_after == 150", br and br[-1].balance_after == 150)
    db.close()

    # --- vault lock (-crystals) ---
    db = TestingSessionLocal()
    dom = models.Domain(
        owner_id=uid, geometry_json="[]", area_sqkm=0.5, defense_score=10,
        defense_type="pushups", vault_balance=0,
    )
    db.add(dom)
    db.commit()
    dom_id = dom.id
    db.close()

    r = client.post(f"/api/v1/domains/{dom_id}/vault", headers=_auth(uid), json={
        "user_id": uid, "amount": 40,
    })
    _check("vault lock -> 200", r.status_code == 200)

    db = TestingSessionLocal()
    vl = [x for x in _ledger_rows(db, uid) if x.reason_code == "vault_lock"]
    _check("vault_lock row written with delta -40",
           len(vl) == 1 and vl[0].delta == -40 and vl[0].related_domain_id == dom_id)
    _check("vault_lock balance_after == 110", vl and vl[-1].balance_after == 110)
    db.close()

    # --- siege WIN on a PAID domain (out_of_pocket debit + win payout credit) ---
    db = TestingSessionLocal()
    defender = _make_user_direct(db, "ledger_defender@test.com", crystals=0)
    ddom = models.Domain(
        owner_id=defender.id, geometry_json="[]", area_sqkm=0.3, defense_score=5,
        defense_type="pushups", vault_balance=20,
    )
    db.add(ddom)
    db.commit()
    ddom_id = ddom.id
    siege = models.SiegeLog(
        challenger_id=uid, target_domain_id=ddom_id, status="pending_feat",
        defender_score_snapshot=5, challenger_fee=0,
    )
    db.add(siege)
    db.commit()
    siege_id = siege.id
    wallet_before = db.get(models.User, uid).mana_crystals
    db.close()

    r = client.post(f"/api/v1/sieges/{siege_id}/resolve", headers=_auth(uid), json={
        "challenger_score": 10, "device_timestamp": _now_str(),
    })
    _check("siege resolve -> 200", r.status_code == 200)
    _check("siege won (10 > 5 on pushups)", r.status_code == 200 and r.json()["status"] == "won")

    db = TestingSessionLocal()
    rows = _ledger_rows(db, uid)
    oop = [x for x in rows if x.reason_code == "siege_out_of_pocket"]
    payout = [x for x in rows if x.reason_code == "siege_win_payout"]
    _check("siege_out_of_pocket row delta -20", len(oop) == 1 and oop[0].delta == -20)
    _check("siege_win_payout row written (positive)", len(payout) == 1 and payout[0].delta > 0)

    u = db.get(models.User, uid)
    # Conservation: the wallet equals the sum of every ledger delta for this user.
    _check("conservation: sum(deltas) == mana_crystals", _ledger_sum(db, uid) == u.mana_crystals)
    # balance_after on every row equals the running cumulative sum of deltas.
    running = 0
    ok_running = True
    for row in rows:
        running += row.delta
        if row.balance_after != running:
            ok_running = False
    _check("every row's balance_after == running cumulative balance", ok_running)
    # Win math sanity: started at wallet_before, -20 out-of-pocket, + payout.
    _check("net change == payout - 20",
           u.mana_crystals == wallet_before - 20 + payout[0].delta)
    db.close()


# --- Test 3 (§3.1): a free-tier time-trial domain is now conquerable ------------------------
def test_free_tier_time_trial_conquerable():
    uid = _onboard("ledger_tt_challenger@test.com")
    db = TestingSessionLocal()
    defender = _make_user_direct(db, "ledger_tt_defender@test.com", crystals=0)
    free_dom = models.Domain(
        owner_id=defender.id, geometry_json="[]", area_sqkm=0.4, defense_score=0,
        defense_type="run", vault_balance=0,   # free tier: no vault, no baseline
    )
    db.add(free_dom)
    db.commit()
    fdom_id = free_dom.id
    siege = models.SiegeLog(
        challenger_id=uid, target_domain_id=fdom_id, status="pending_feat",
        defender_score_snapshot=0, challenger_fee=0,   # free tier baseline == 0
    )
    db.add(siege)
    db.commit()
    siege_id = siege.id
    db.close()

    # A positive time-trial score must WIN. On the pre-fix code this resolved to "failed"
    # because `score <= 0 and score > 0` is always False.
    r = client.post(f"/api/v1/sieges/{siege_id}/resolve", headers=_auth(uid), json={
        "challenger_score": 300, "device_timestamp": _now_str(),
    })
    _check("free-tier time-trial resolve -> 200", r.status_code == 200)
    _check("§3.1 free-tier time-trial domain conquerable by positive score",
           r.status_code == 200 and r.json()["status"] == "won")


# --- Test 4: reconciliation check passes for every user after all operations ----------------
def test_reconciliation_check_passes():
    db = TestingSessionLocal()
    try:
        bad = reconcile.check(db)
        _check("reconcile.check finds zero discrepancies across all users", bad == 0)
    finally:
        db.close()


# --- Test 5: orphaned ledger rows are reported (PLAN item 1 regression) ---------------------
def test_orphan_ledger_rows_are_reported():
    """Deleting a user but not their ledger rows leaves orphans. SQLite reuses the freed id,
    so the next account silently inherits that history and reconciliation fails much later
    for an unrelated user. The check must flag orphans as soon as they exist."""
    uid = _onboard("ledger_orphan@example.com")
    db = TestingSessionLocal()
    try:
        db.query(models.User).filter(models.User.id == uid).delete(synchronize_session=False)
        db.commit()
        _check("reconcile.check reports a ledger row whose user was deleted", reconcile.check(db) >= 1)
        db.query(models.CrystalLedger).filter(models.CrystalLedger.user_id == uid).delete(synchronize_session=False)
        db.commit()
        _check("reconcile.check is clean once the orphan rows are removed", reconcile.check(db) == 0)
    finally:
        db.close()


if __name__ == "__main__":
    print("--- Phase 2 Crystal Ledger tests ---")
    test_opening_balance_row()
    test_full_money_path_conservation()
    test_free_tier_time_trial_conquerable()
    test_reconciliation_check_passes()  # checks all users created above
    test_orphan_ledger_rows_are_reported()
    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} check(s) FAILED: {_FAILURES}")
        sys.exit(1)
    print("All Phase 2 ledger checks passed.")
