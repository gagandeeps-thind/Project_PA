"""Service layer for Osiris backend.

Thin, transaction-agnostic helpers that own a single business invariant each. Services
NEVER commit — the calling endpoint owns the transaction boundary.
"""
