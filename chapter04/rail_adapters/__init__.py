"""Rail adapters: one shared case model driven by a profile per payment rail (Chapter 4)."""

from .base import RailCase, RailProfile
from .profiles import ACH_DEBIT, INSTANT, PUSH_RECOVERY, WIRE

__all__ = ["RailCase", "RailProfile", "ACH_DEBIT", "INSTANT", "WIRE", "PUSH_RECOVERY"]
