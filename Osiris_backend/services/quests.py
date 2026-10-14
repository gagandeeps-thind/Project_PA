"""Daily quest, weekly goal, and streak rules for the core habit loop (growth release G1).

Pure functions only: no database session, no HTTP. `growth_api.py` loads the player's
accepted runs, calls these, and owns the transaction.

Design constraints (product brief, "healthy habit, not addiction"):
- Rest never breaks anything. The streak is counted in *weeks* that met a small
  active-day target, so skipping a day, or several, costs nothing while the week can
  still be met.
- Quests scale from the player's own verified history and are capped. They never ask for
  more than 125% of the player's best recent day or more than 10 km.
- After three active days in a row the recommendation becomes an optional recovery walk.
- Rewards are XP only. Nothing is lost for missing a quest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Iterable, Mapping

QUEST_RULES_VERSION = "quest-rules-v1"

GOALS = ("fitness", "running", "consistency", "competition")
DEFAULT_GOAL = "fitness"

# Plain-language identity shown on the profile. The fantasy flavour lives in the theme,
# not in the words a new user has to learn.
GOAL_IDENTITY = {
    "fitness": "athlete",
    "running": "runner",
    "consistency": "explorer",
    "competition": "challenger",
}

# Daily target as a fraction of the player's typical active-day distance.
GOAL_FACTOR = {"fitness": 0.9, "running": 1.0, "consistency": 0.75, "competition": 1.05}
# Active days that complete a week. Small on purpose: three days is a real habit.
WEEKLY_ACTIVE_DAYS = {"fitness": 3, "running": 3, "consistency": 3, "competition": 4}

HISTORY_DAYS = 28
STARTER_TARGET_M = 1_000
RECOVERY_TARGET_M = 1_000
MIN_TARGET_M = 800
MAX_TARGET_M = 10_000
MAX_GROWTH_OVER_BEST = 1.25
EASY_DAY_FACTOR = 0.6
RECOVERY_AFTER_ACTIVE_DAYS = 3

DAILY_XP_BASE = 20
DAILY_XP_PER_KM = 5
DAILY_XP_CAP = 80
WEEKLY_XP = 50

SAFETY_NOTE = (
    "Go at a pace where you can still talk. Stay on paths you know, keep to lit public "
    "areas, and stop if you feel pain or dizziness. Rest days never cost you anything."
)


@dataclass(frozen=True)
class DailyQuest:
    key: str
    local_date: date
    kind: str            # starter | steady | easy | recovery
    title: str
    description: str
    target_m: int
    xp: int
    optional: bool


@dataclass(frozen=True)
class WeeklyGoal:
    key: str
    week_start: date
    active_days_target: int
    active_days: int
    distance_m: float
    xp: int
    completed: bool


def normalize_goal(goal: str | None) -> str:
    return goal if goal in GOALS else DEFAULT_GOAL


def identity_for(goal: str | None) -> str:
    return GOAL_IDENTITY[normalize_goal(goal)]


def local_date(utc_dt: datetime, utc_offset_minutes: int) -> date:
    """Local calendar date for a naive-UTC timestamp."""
    return (utc_dt + timedelta(minutes=utc_offset_minutes)).date()


def daily_key(d: date) -> str:
    return f"daily:{d.isoformat()}"


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_key(d: date) -> str:
    iso = d.isocalendar()
    return f"weekly:{iso[0]}-W{iso[1]:02d}"


def daily_totals(runs: Iterable[tuple[datetime, float]], utc_offset_minutes: int) -> dict[date, float]:
    """Sum accepted-run distance per local date. `runs` is (finished_at_utc, distance_m)."""
    totals: dict[date, float] = {}
    for finished_at, distance in runs:
        d = local_date(finished_at, utc_offset_minutes)
        totals[d] = totals.get(d, 0.0) + float(distance or 0.0)
    return totals


def _round_100(metres: float) -> int:
    return int(round(metres / 100.0)) * 100


def _xp_for(target_m: int) -> int:
    return min(DAILY_XP_CAP, DAILY_XP_BASE + int(target_m / 1000 * DAILY_XP_PER_KM))


def daily_quest(goal: str | None, today: date, totals: Mapping[date, float]) -> DailyQuest:
    """Today's recommended quest. Only days *before* today feed the target, so the quest
    does not move while the player is completing it."""
    goal = normalize_goal(goal)
    history = {
        d: m for d, m in totals.items()
        if today - timedelta(days=HISTORY_DAYS) <= d < today and m > 0
    }
    key = daily_key(today)

    if not history:
        return DailyQuest(
            key=key, local_date=today, kind="starter",
            title="Walk or run 1 km",
            description="Your first quest: move 1 km at any pace. Walking counts.",
            target_m=STARTER_TARGET_M, xp=_xp_for(STARTER_TARGET_M), optional=False,
        )

    streak_days = 0
    d = today - timedelta(days=1)
    while history.get(d, 0) > 0:
        streak_days += 1
        d -= timedelta(days=1)
    if streak_days >= RECOVERY_AFTER_ACTIVE_DAYS:
        return DailyQuest(
            key=key, local_date=today, kind="recovery",
            title="Recovery day: easy 1 km walk",
            description="You've been active three days running. Take an easy walk or rest; both are fine.",
            target_m=RECOVERY_TARGET_M, xp=_xp_for(RECOVERY_TARGET_M), optional=True,
        )

    typical = median(history.values())
    best = max(history.values())
    target = typical * GOAL_FACTOR[goal]
    # One easy day a week (Wednesday) keeps the plan varied without asking for more.
    kind = "easy" if today.weekday() == 2 else "steady"
    if kind == "easy":
        target *= EASY_DAY_FACTOR
    target = min(target, best * MAX_GROWTH_OVER_BEST, MAX_TARGET_M)
    target_m = max(MIN_TARGET_M, _round_100(target))
    km = target_m / 1000
    title = f"{'Easy' if kind == 'easy' else 'Move'} {km:g} km"
    description = (
        "An easy day. Keep it relaxed." if kind == "easy"
        else "Based on your recent verified activity. Walk, jog, or run."
    )
    return DailyQuest(
        key=key, local_date=today, kind=kind, title=title, description=description,
        target_m=target_m, xp=_xp_for(target_m), optional=False,
    )


def quest_progress(quest: DailyQuest, totals: Mapping[date, float]) -> tuple[float, bool]:
    done = float(totals.get(quest.local_date, 0.0))
    return done, done >= quest.target_m


def weekly_goal(goal: str | None, today: date, totals: Mapping[date, float]) -> WeeklyGoal:
    goal = normalize_goal(goal)
    start = week_start(today)
    days = [start + timedelta(days=i) for i in range(7)]
    active = [d for d in days if totals.get(d, 0) > 0]
    target = WEEKLY_ACTIVE_DAYS[goal]
    return WeeklyGoal(
        key=weekly_key(today), week_start=start, active_days_target=target,
        active_days=len(active), distance_m=sum(totals.get(d, 0.0) for d in days),
        xp=WEEKLY_XP, completed=len(active) >= target,
    )


def weekly_streak(goal: str | None, today: date, totals: Mapping[date, float]) -> int:
    """Consecutive weeks that met the active-day target. The current week adds to the
    streak once met but never breaks it while it is still in progress."""
    goal = normalize_goal(goal)
    target = WEEKLY_ACTIVE_DAYS[goal]

    def met(start: date) -> bool:
        return sum(1 for i in range(7) if totals.get(start + timedelta(days=i), 0) > 0) >= target

    this_week = week_start(today)
    streak = 1 if met(this_week) else 0
    w = this_week - timedelta(days=7)
    while met(w):
        streak += 1
        w -= timedelta(days=7)
    return streak
