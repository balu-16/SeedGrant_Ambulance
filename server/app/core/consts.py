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

# Command statuses that still require action (not terminal yet) — used by the
# portal live view and the manual-override logic.
OPEN_COMMAND_STATUSES = ("PENDING", "SENT", "ACKNOWLEDGED")
