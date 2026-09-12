"""Shared enums + constants (mirrors DB enums to avoid drift)."""

# CREATED and APPROACHING_JUNCTION are reserved per spec; sessions currently begin ACTIVE.
ACTIVE_SESSION_STATUSES = (
    "CREATED",
    "ACTIVE",
    "APPROACHING_JUNCTION",
    "PRIORITY_REQUESTED",
    "CROSSING",
)
TERMINAL_SESSION_STATUSES = ("COMPLETED", "CANCELLED", "TIMED_OUT")
