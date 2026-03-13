"""
ARI Push Engine — MongoDB collection names and document shapes.
"""

# Collection names
COLL_ARI_EVENTS = "ari_events"
COLL_ARI_CHANGE_SETS = "ari_change_sets"
COLL_ARI_OUTBOUND_LOGS = "ari_outbound_logs"
COLL_ARI_DRIFT_STATE = "ari_drift_state"

# Status constants
STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"
STATUS_PUSHED = "pushed"
STATUS_ACKED = "acked"
STATUS_FAILED_RETRYABLE = "failed_retryable"
STATUS_FAILED_PERMANENT = "manual_review"
STATUS_SKIPPED = "skipped"

# Event types
EVENT_AVAILABILITY = "availability"
EVENT_RATE = "rate"
EVENT_RESTRICTION = "restriction"

# Debounce windows (seconds) per event type
DEBOUNCE_WINDOWS = {
    EVENT_AVAILABILITY: 2,
    EVENT_RATE: 5,
    EVENT_RESTRICTION: 3,
}

# Retry policy: delay in seconds per attempt
RETRY_DELAYS = [0, 10, 30, 120, 300]  # immediate, 10s, 30s, 2min, 5min
MAX_RETRY_ATTEMPTS = 5
