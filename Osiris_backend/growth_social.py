"""Growth release G2: sharing, invite-a-friend challenges, referrals, public pages.

The loop this serves: complete a challenge -> share the result -> a friend opens the link
-> signs up through it -> joins the same challenge.

Privacy rules for everything public here (Security §2-3, ADR-004):
- No route, start/finish point, map, or coordinates. Ever.
- Share cards show only distance, time, pace, and badge, and the owner can revoke them.
- Achievement pages are opt-in (`PlayerProfile.public_profile`) and show aggregate stats.
- Share and invite tokens are random and unguessable; ids never appear in public URLs.

Registered on `main.app` at the bottom of this module (see growth_api for the pattern).
"""
from __future__ import annotations

import html
import json
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import settings
from growth_api import (
    REFERRAL_CAP,
    REFERRAL_CAP_WINDOW_DAYS,
    REFERRAL_MIN_DISTANCE_M,
    REFERRAL_XP,
    TAGLINE,
    _daily_totals,
    emit_event,
    get_or_create_profile,
)
from main import (
    _api_error,
    _now_naive_utc,
    _refresh_challenge_status,
    app,
    get_active_player,
    get_db,
)
from services import challenges as challenge_rules
from services import quests as quest_rules

router = APIRouter()

SHARE_KINDS = ("run", "challenge_result", "quest", "badge")
APP_DEEP_LINK = "osiris://"


def _base_url(request: Request) -> str:
    """Links come from configuration; the request's Host header is used only in dev, since a
    forged Host would otherwise put an attacker's origin into share and invite links."""
    configured = settings.public_base_url()
    if configured:
        return configured
    if settings.is_dev_env():
        return str(request.base_url).rstrip("/")
    raise _api_error(503, "PUBLIC_BASE_URL_UNSET", "Sharing links are not available right now")


def _token() -> str:
    return secrets.token_urlsafe(12)


def _fmt_duration(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _pace(distance_m: float, seconds: Optional[float]) -> Optional[str]:
    if not seconds or distance_m < 100:
        return None
    return _fmt_duration(seconds / (distance_m / 1000.0)) + " /km"


# --- schemas ---------------------------------------------------------------------

class ShareCreate(BaseModel):
    kind: str
    entity_id: int


class ShareCardOut(BaseModel):
    token: str
    url: str
    kind: str
    headline: str
    stats: dict
    share_text: str
    challenge_id: Optional[int] = None
    challenge_open: bool = False
    display_name: str
    created_at: datetime


class InviteOut(BaseModel):
    token: str
    url: str
    share_text: str
    challenge_id: int


class InvitePreview(BaseModel):
    token: str
    inviter_name: str
    challenge_title: str
    challenge_status: str
    course_distance_km: float
    target_time: str
    closes_at: datetime
    free_entry: bool
    safety_notes: Optional[str] = None
    referral_code: str
    app_link: str


class InviteStats(BaseModel):
    token: str
    challenge_id: int
    challenge_title: str
    opens: int
    signups: int
    joins: int


class ReferralSummary(BaseModel):
    referral_code: str
    url: str
    pending: int
    rewarded: int
    not_rewarded: int
    rules: List[str]


class PublicBadge(BaseModel):
    code: str
    label: str
    awarded_at: datetime


class PublicPlayer(BaseModel):
    display_name: str
    identity: str
    performance_rank: str
    xp: int
    verified_runs: int
    total_distance_km: float
    streak_weeks: int
    challenges_won: int
    badges: List[PublicBadge]
    member_since: datetime
    url: str


# --- share cards -----------------------------------------------------------------

def _build_card(db: Session, user_id: int, name: str, kind: str, entity_id: int) -> tuple[str, dict, Optional[int]]:
    """Validate ownership and build (headline, stats, challenge_id) for a share card."""
    if kind == "run":
        run = db.query(models.RunSession).filter(
            models.RunSession.id == entity_id, models.RunSession.user_id == user_id,
        ).first()
        if run is None or run.verification_status != "accepted":
            raise _api_error(404, "NOT_SHAREABLE", "Only your own verified runs can be shared")
        km = round((run.distance_m or 0) / 1000.0, 2)
        stats = {"distance_km": km, "time": _fmt_duration(run.duration_seconds),
                 "pace": _pace(run.distance_m or 0, run.duration_seconds), "verified": True}
        return f"{name} moved {km:g} km", stats, None
    if kind == "challenge_result":
        attempt = db.query(models.ChallengeAttempt).filter(
            models.ChallengeAttempt.id == entity_id, models.ChallengeAttempt.user_id == user_id,
        ).first()
        if attempt is None or attempt.status != "accepted" or attempt.outcome not in ("won", "lost"):
            raise _api_error(404, "NOT_SHAREABLE", "Only your own verified challenge results can be shared")
        ch = db.query(models.Challenge).filter(models.Challenge.id == attempt.challenge_id).first()
        course = db.query(models.Course).filter(models.Course.id == ch.course_id).first()
        km = round(course.distance_m / 1000.0, 2)
        verb = "beat the target on" if attempt.outcome == "won" else "completed"
        stats = {"distance_km": km, "time": _fmt_duration(attempt.elapsed_seconds),
                 "target": _fmt_duration(ch.target_seconds), "outcome": attempt.outcome,
                 "challenge": ch.title, "verified": True}
        return f"{name} {verb} “{ch.title}”", stats, ch.id
    if kind == "quest":
        award = db.query(models.QuestAward).filter(
            models.QuestAward.id == entity_id, models.QuestAward.user_id == user_id,
        ).first()
        if award is None:
            raise _api_error(404, "NOT_SHAREABLE", "Quest award not found")
        if award.quest_key.startswith("weekly:"):
            return f"{name} met this week's goal", {"quest": award.quest_key, "xp": award.xp_awarded}, None
        km = (award.target_m or 0) / 1000.0
        return f"{name} completed today's quest", {"quest": award.quest_key, "target_km": km,
                                                    "xp": award.xp_awarded}, None
    if kind == "badge":
        badge = db.query(models.UserBadge).filter(
            models.UserBadge.id == entity_id, models.UserBadge.user_id == user_id,
        ).first()
        if badge is None:
            raise _api_error(404, "NOT_SHAREABLE", "Badge not found")
        label = challenge_rules.BADGES.get(badge.badge_code, badge.badge_code)
        return f"{name} earned “{label}”", {"badge": badge.badge_code, "label": label}, None
    raise _api_error(422, "INVALID_KIND", f"kind must be one of {', '.join(SHARE_KINDS)}")


def _card_out(db: Session, card: models.ShareCard, request: Request, name: str) -> ShareCardOut:
    url = f"{_base_url(request)}/s/{card.token}"
    challenge_open = False
    if card.challenge_id:
        ch = db.query(models.Challenge).filter(models.Challenge.id == card.challenge_id).first()
        challenge_open = ch is not None and ch.status == "open"
    text = f"{card.headline} on Osiris. {TAGLINE}"
    if challenge_open:
        text += " Think you can do it? Take the same challenge:"
    return ShareCardOut(
        token=card.token, url=url, kind=card.kind, headline=card.headline,
        stats=json.loads(card.stats_json or "{}"), share_text=f"{text} {url}",
        challenge_id=card.challenge_id, challenge_open=challenge_open, display_name=name,
        created_at=card.created_at,
    )


def _display_name(db: Session, user_id: int) -> str:
    p = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == user_id).first()
    return p.display_name if p else f"Runner {user_id}"


@router.post("/api/v2/share", response_model=ShareCardOut, status_code=201)
def create_share_card(
    req: ShareCreate, request: Request, db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """Create (or return) the share card for one of the player's achievements.
    Idempotent per (kind, entity). A revoked card is re-activated with a fresh token."""
    user_id = token_data["id"]
    user = db.query(models.User).filter(models.User.id == user_id).first()
    profile = get_or_create_profile(db, user)
    headline, stats, challenge_id = _build_card(db, user_id, profile.display_name, req.kind, req.entity_id)
    card = db.query(models.ShareCard).filter(
        models.ShareCard.user_id == user_id, models.ShareCard.kind == req.kind,
        models.ShareCard.entity_id == req.entity_id,
    ).first()
    if card is None:
        card = models.ShareCard(
            token=_token(), user_id=user_id, kind=req.kind, entity_id=req.entity_id,
            headline=headline, stats_json=json.dumps(stats, sort_keys=True), challenge_id=challenge_id,
        )
        db.add(card)
        emit_event(db, "share_created", user_id=user_id, properties={"kind": req.kind})
    elif card.revoked_at is not None:
        card.revoked_at = None
        card.token = _token()
    db.commit()
    db.refresh(card)
    return _card_out(db, card, request, profile.display_name)


@router.delete("/api/v2/share/{token}", status_code=204)
def revoke_share_card(token: str, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    card = db.query(models.ShareCard).filter(models.ShareCard.token == token).first()
    if card is None or card.user_id != token_data["id"]:
        raise _api_error(404, "SHARE_NOT_FOUND", "Share card not found")
    card.revoked_at = _now_naive_utc()
    db.commit()


def _live_card(db: Session, token: str) -> models.ShareCard:
    card = db.query(models.ShareCard).filter(models.ShareCard.token == token).first()
    if card is None or card.revoked_at is not None:
        raise _api_error(404, "SHARE_NOT_FOUND", "This share link is no longer available")
    owner = db.query(models.User).filter(models.User.id == card.user_id).first()
    if owner is None or owner.suspended_at is not None:
        raise _api_error(404, "SHARE_NOT_FOUND", "This share link is no longer available")
    return card


@router.get("/api/v2/share/{token}", response_model=ShareCardOut)
def get_share_card(token: str, request: Request, db: Session = Depends(get_db)):
    """Public: the card behind a share link. No authentication."""
    card = _live_card(db, token)
    card.view_count = (card.view_count or 0) + 1
    db.commit()
    return _card_out(db, card, request, _display_name(db, card.user_id))


# --- invite-a-friend challenges ------------------------------------------------------

@router.post("/api/v2/challenges/{challenge_id}/invites", response_model=InviteOut, status_code=201)
def create_challenge_invite(
    challenge_id: int, request: Request, db: Session = Depends(get_db),
    token_data: dict = Depends(get_active_player),
):
    """One invite link per (challenge, inviter). Anyone may invite friends to an open
    challenge; the link also carries the inviter's referral."""
    ch = db.query(models.Challenge).filter(models.Challenge.id == challenge_id).first()
    if ch is None:
        raise _api_error(404, "CHALLENGE_NOT_FOUND", "Challenge not found")
    if _refresh_challenge_status(db, ch):
        db.commit()
    if ch.status != "open":
        raise _api_error(409, "CHALLENGE_NOT_OPEN", f"Challenge is {ch.status}")
    user = db.query(models.User).filter(models.User.id == token_data["id"]).first()
    get_or_create_profile(db, user)
    invite = db.query(models.ChallengeInvite).filter(
        models.ChallengeInvite.challenge_id == ch.id, models.ChallengeInvite.inviter_id == user.id,
    ).first()
    if invite is None:
        invite = models.ChallengeInvite(token=_token(), challenge_id=ch.id, inviter_id=user.id)
        db.add(invite)
        emit_event(db, "invite_sent", user_id=user.id, properties={"challenge_id": ch.id})
    db.commit()
    url = f"{_base_url(request)}/i/{invite.token}"
    return InviteOut(
        token=invite.token, url=url, challenge_id=ch.id,
        share_text=f"Join me on “{ch.title}” on Osiris. It's free. {url}",
    )


def _invite_preview(db: Session, token: str) -> tuple[models.ChallengeInvite, InvitePreview]:
    invite = db.query(models.ChallengeInvite).filter(models.ChallengeInvite.token == token).first()
    if invite is None:
        raise _api_error(404, "INVITE_NOT_FOUND", "That invite link was not found")
    ch = db.query(models.Challenge).filter(models.Challenge.id == invite.challenge_id).first()
    course = db.query(models.Course).filter(models.Course.id == ch.course_id).first()
    if _refresh_challenge_status(db, ch):
        db.flush()
    inviter = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == invite.inviter_id).first()
    return invite, InvitePreview(
        token=invite.token, inviter_name=inviter.display_name if inviter else "A friend",
        challenge_title=ch.title, challenge_status=ch.status,
        course_distance_km=round(course.distance_m / 1000.0, 2),
        target_time=_fmt_duration(ch.target_seconds), closes_at=ch.closes_at,
        free_entry=(ch.entry_crystals or 0) == 0, safety_notes=ch.safety_notes,
        referral_code=inviter.referral_code if inviter else "",
        app_link=f"{APP_DEEP_LINK}invite/{invite.token}",
    )


@router.get("/api/v2/invites/{token}", response_model=InvitePreview)
def get_invite(token: str, db: Session = Depends(get_db)):
    """Public preview of an invite. No coordinates: the exact course is shown only to
    players who join, as for any challenge."""
    invite, preview = _invite_preview(db, token)
    invite.opens = (invite.opens or 0) + 1
    db.commit()
    return preview


@router.get("/api/v2/me/invites", response_model=List[InviteStats])
def my_invites(db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    """How each of the player's invite links performed. A join counts a friend who signed
    up through the inviter and then joined that challenge."""
    uid = token_data["id"]
    referred = [
        p for (p,) in db.query(models.PlayerProfile.user_id)
        .filter(models.PlayerProfile.referred_by_user_id == uid).all()
    ]
    invites = db.query(models.ChallengeInvite).filter(models.ChallengeInvite.inviter_id == uid).order_by(
        models.ChallengeInvite.id.asc()).limit(200).all()
    challenge_ids = [i.challenge_id for i in invites] or [-1]
    titles = {cid: title for cid, title in db.query(models.Challenge.id, models.Challenge.title).filter(
        models.Challenge.id.in_(challenge_ids))}
    joins = {cid: n for cid, n in db.query(models.ChallengeAttempt.challenge_id, func.count(models.ChallengeAttempt.id))
             .filter(models.ChallengeAttempt.challenge_id.in_(challenge_ids),
                     models.ChallengeAttempt.user_id.in_(referred or [-1]))
             .group_by(models.ChallengeAttempt.challenge_id).all()}
    return [InviteStats(token=invite.token, challenge_id=invite.challenge_id,
                        challenge_title=titles.get(invite.challenge_id, ""), opens=invite.opens or 0,
                        signups=invite.signups or 0, joins=joins.get(invite.challenge_id, 0))
            for invite in invites]


@router.get("/api/v2/me/referrals", response_model=ReferralSummary)
def my_referrals(request: Request, db: Session = Depends(get_db), token_data: dict = Depends(get_active_player)):
    uid = token_data["id"]
    user = db.query(models.User).filter(models.User.id == uid).first()
    profile = get_or_create_profile(db, user)
    db.commit()
    rows = db.query(models.PlayerProfile.referral_status).filter(
        models.PlayerProfile.referred_by_user_id == uid,
    ).all()
    statuses = [s for (s,) in rows]
    return ReferralSummary(
        referral_code=profile.referral_code,
        url=f"{_base_url(request)}/join/{profile.referral_code}",
        pending=statuses.count("pending"), rewarded=statuses.count("rewarded"),
        not_rewarded=sum(1 for s in statuses if s in ("capped", "same_device")),
        rules=[
            f"You earn {REFERRAL_XP} XP and the Recruiter badge when a friend you invited completes "
            f"a verified run of at least {REFERRAL_MIN_DISTANCE_M // 1000} km.",
            "Signing up alone earns nothing. The run has to happen.",
            f"Up to {REFERRAL_CAP} rewarded friends every {REFERRAL_CAP_WINDOW_DAYS} days.",
            "Accounts created from your own device don't count.",
            "Rewards are XP and badges only. There is no cash or crystal value.",
        ],
    )


# --- public achievement pages ------------------------------------------------------------

def _public_player(db: Session, code: str, request: Request) -> PublicPlayer:
    profile = db.query(models.PlayerProfile).filter(models.PlayerProfile.referral_code == code.upper()).first()
    user = db.query(models.User).filter(models.User.id == profile.user_id).first() if profile else None
    if profile is None or not profile.public_profile or user is None or user.suspended_at is not None:
        raise _api_error(404, "PROFILE_NOT_PUBLIC", "This profile is private or does not exist")
    runs = db.query(models.RunSession.distance_m).filter(
        models.RunSession.user_id == user.id, models.RunSession.verification_status == "accepted",
    ).all()
    now = _now_naive_utc()
    totals = _daily_totals(db, user.id, profile.utc_offset_minutes or 0, now)
    today = quest_rules.local_date(now, profile.utc_offset_minutes or 0)
    badges = db.query(models.UserBadge).filter(models.UserBadge.user_id == user.id).order_by(
        models.UserBadge.awarded_at.asc()).all()
    xp = user.xp or 0
    return PublicPlayer(
        display_name=profile.display_name, identity=quest_rules.identity_for(profile.goal),
        performance_rank=challenge_rules.performance_rank(xp), xp=xp, verified_runs=len(runs),
        total_distance_km=round(sum(d or 0 for (d,) in runs) / 1000.0, 1),
        streak_weeks=quest_rules.weekly_streak(profile.goal, today, totals),
        challenges_won=db.query(models.ChallengeAttempt).filter(
            models.ChallengeAttempt.user_id == user.id, models.ChallengeAttempt.outcome == "won").count(),
        badges=[PublicBadge(code=b.badge_code, label=challenge_rules.BADGES.get(b.badge_code, b.badge_code),
                            awarded_at=b.awarded_at) for b in badges],
        member_since=profile.created_at, url=f"{_base_url(request)}/p/{profile.referral_code}",
    )


@router.get("/api/v2/public/players/{code}", response_model=PublicPlayer)
def public_player(code: str, request: Request, db: Session = Depends(get_db)):
    return _public_player(db, code, request)


# --- server-rendered pages (search and link previews) ------------------------------------

_PAGE_CSS = """
:root{--bg:#f6f5f2;--fg:#1d1b18;--muted:#6b665e;--card:#fff;--accent:#c2410c;--line:#e7e2da}
@media (prefers-color-scheme:dark){:root{--bg:#141210;--fg:#f3efe8;--muted:#a59e93;--card:#1f1c19;--accent:#fb923c;--line:#2f2a25}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:560px;margin:0 auto;padding:32px 16px}.brand{color:var(--accent);font-weight:700;letter-spacing:.04em;text-transform:uppercase;font-size:13px}
h1{font-size:28px;line-height:1.2;margin:8px 0 4px}.sub{color:var(--muted);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:12px}.stat b{display:block;font-size:22px}
.stat span{color:var(--muted);font-size:13px}ul{padding-left:18px}.cta{display:inline-block;background:var(--accent);color:#fff;
padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:600;margin-top:8px}.foot{color:var(--muted);font-size:13px;margin-top:28px}
"""


def _page(*, title: str, description: str, url: str, body: str, index: bool,
          jsonld: Optional[dict] = None, status_code: int = 200) -> HTMLResponse:
    e = html.escape
    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld).replace("</", "<\\/") + "</script>"
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description)}">
<meta name="robots" content="{'index,follow' if index else 'noindex,nofollow'}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Osiris">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{e(url)}"><meta name="twitter:card" content="summary">
<style>{_PAGE_CSS}</style>{ld}</head><body><main><div class="brand">Osiris · {e(TAGLINE)}</div>
{body}<p class="foot">Osiris checks each run's GPS route for realistic speed, gaps, and accuracy before it counts.
No route or location is shown on this page.</p></main></body></html>"""
    return HTMLResponse(doc, status_code=status_code)


def _stat(value, label: str) -> str:
    return f'<div class="stat"><b>{html.escape(str(value))}</b><span>{html.escape(label)}</span></div>'


def _not_found(url: str) -> HTMLResponse:
    return _page(title="Not available · Osiris", description="This link is private or no longer available.",
                 url=url, index=False, status_code=404,
                 body="<h1>This link isn't available</h1><p class='sub'>It may be private or removed.</p>")


@router.get("/s/{token}", include_in_schema=False)
def share_page(token: str, request: Request, db: Session = Depends(get_db)):
    url = f"{_base_url(request)}/s/{token}"
    try:
        card = _live_card(db, token)
    except HTTPException:
        return _not_found(url)
    card.view_count = (card.view_count or 0) + 1
    db.commit()
    out = _card_out(db, card, request, _display_name(db, card.user_id))
    labels = {"distance_km": "km", "time": "time", "pace": "pace", "target": "target",
              "target_km": "quest km", "xp": "XP", "label": "badge"}
    stats = "".join(_stat(v, labels[k]) for k, v in out.stats.items() if k in labels and v is not None)
    cta = ""
    if out.challenge_open:
        cta = (f'<a class="cta" href="{APP_DEEP_LINK}challenge/{out.challenge_id}">Take the same challenge</a>')
    body = (f"<h1>{html.escape(out.headline)}</h1><p class='sub'>Verified on Osiris</p>"
            f"<div class='card'><div class='stats'>{stats}</div></div>{cta}")
    # Share cards are for people with the link, not for search indexes.
    return _page(title=f"{out.headline} · Osiris", description=f"{out.headline}. {TAGLINE}",
                 url=url, body=body, index=False)


@router.get("/i/{token}", include_in_schema=False)
def invite_page(token: str, request: Request, db: Session = Depends(get_db)):
    url = f"{_base_url(request)}/i/{token}"
    try:
        invite, p = _invite_preview(db, token)
    except HTTPException:
        return _not_found(url)
    invite.opens = (invite.opens or 0) + 1
    db.commit()
    e = html.escape
    status = "" if p.challenge_status == "open" else f"<p class='sub'>This challenge is {e(p.challenge_status)}.</p>"
    body = (f"<h1>{e(p.inviter_name)} invited you to “{e(p.challenge_title)}”</h1>"
            f"<p class='sub'>Free to enter. Run it any time before it closes.</p>{status}"
            f"<div class='card'><div class='stats'>{_stat(p.course_distance_km, 'km')}"
            f"{_stat(p.target_time, 'time to beat')}</div></div>"
            f"<div class='card'><b>Safety</b><p>{e(p.safety_notes or quest_rules.SAFETY_NOTE)}</p></div>"
            f"<a class='cta' href='{e(p.app_link)}'>Open in Osiris</a>")
    return _page(title=f"Join “{p.challenge_title}” · Osiris",
                 description=f"{p.inviter_name} invited you to a {p.course_distance_km} km running challenge on Osiris.",
                 url=url, body=body, index=False)


@router.get("/p/{code}", include_in_schema=False)
def player_page(code: str, request: Request, db: Session = Depends(get_db)):
    """Opt-in public achievement page, built for search and link previews."""
    url = f"{_base_url(request)}/p/{code}"
    try:
        p = _public_player(db, code, request)
    except HTTPException:
        return _not_found(url)
    e = html.escape
    badges = "".join(f"<li>{e(b.label)}</li>" for b in p.badges) or "<li>No badges yet</li>"
    description = (f"{p.display_name} is a {p.performance_rank} {p.identity} on Osiris with "
                   f"{p.verified_runs} verified runs and {p.total_distance_km} km.")
    body = (f"<h1>{e(p.display_name)}</h1><p class='sub'>{e(p.performance_rank)} · {e(p.identity.title())}</p>"
            f"<div class='card'><div class='stats'>{_stat(p.verified_runs, 'verified runs')}"
            f"{_stat(p.total_distance_km, 'km total')}{_stat(p.streak_weeks, 'week streak')}"
            f"{_stat(p.challenges_won, 'challenges won')}{_stat(p.xp, 'XP')}</div></div>"
            f"<div class='card'><b>Achievements</b><ul>{badges}</ul></div>")
    jsonld = {
        "@context": "https://schema.org", "@type": "ProfilePage", "url": p.url,
        "mainEntity": {"@type": "Person", "name": p.display_name, "description": description},
    }
    return _page(title=f"{p.display_name} · {p.performance_rank} {p.identity} · Osiris",
                 description=description, url=p.url, body=body, index=True, jsonld=jsonld)


@router.get("/join/{code}", include_in_schema=False)
def join_page(code: str, request: Request, db: Session = Depends(get_db)):
    """Referral landing page. Names the inviter only if their profile is public."""
    url = f"{_base_url(request)}/join/{code}"
    profile = db.query(models.PlayerProfile).filter(models.PlayerProfile.referral_code == code.upper()).first()
    if profile is None:
        return _not_found(url)
    who = html.escape(profile.display_name) if profile.public_profile else "A friend"
    body = (f"<h1>{who} invited you to Osiris</h1>"
            "<p class='sub'>Daily running and walking quests near you. Free to start.</p>"
            "<div class='card'><ul><li>Pick a goal. No weight or BMI needed.</li>"
            "<li>Get today's quest: usually a short walk or run.</li>"
            "<li>Your route is checked, then your progress counts.</li></ul></div>"
            f"<a class='cta' href='{APP_DEEP_LINK}join/{html.escape(profile.referral_code)}'>Open in Osiris</a>")
    return _page(title="Join Osiris", description=f"{TAGLINE} Free to start.",
                 url=url, body=body, index=False)


app.include_router(router)
