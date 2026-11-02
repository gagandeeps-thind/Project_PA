"""Arise rules: pure functions, no database."""
from typing import Sequence

from services import challenges as rules

LatLng = tuple[float, float]


def public_line(full: Sequence[LatLng], trimmed: Sequence[LatLng], hide_ends: bool) -> list[list[float]]:
    """The line other players see: the privacy-trimmed route, or the whole run when the owner shows the ends."""
    source = trimmed if hide_ends else rules.simplify_route(list(full))
    return [[p[0], p[1]] for p in source]
