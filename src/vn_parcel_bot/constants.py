from datetime import timedelta

PENDING_EXPIRY = timedelta(days=7)
STALE_AFTER = timedelta(days=30)
DELIVERED_VISIBLE_FOR = timedelta(days=3)
PURGE_AFTER = timedelta(days=30)
# 17TRACK refuses registrations once the account's quota is spent. That answer is the
# same for every parcel, so one refusal pauses registrations for this long.
QUOTA_COOLDOWN = timedelta(hours=6)
# Whatever the state or the backoff works out to, no order is left unchecked for longer.
MAX_CHECK_GAP = timedelta(hours=2)
MAX_BACKOFF = MAX_CHECK_GAP
FAILURE_ALERT_THRESHOLD = 5
CARRIER_ALL_FAILED_MIN_FETCHES = 3
ALERT_COOLDOWN = timedelta(hours=6)
ERROR_ALERT_COOLDOWN = timedelta(minutes=30)
CHECK_COOLDOWN = timedelta(minutes=5)
JITTER_SECONDS = 2.0
FIRST_POLL_DELAY_SECONDS = 30
MAX_LABEL_LENGTH = 40
MAX_EVENTS_IN_UPDATE = 10
MAX_EVENTS_IN_HISTORY = 30
TELEGRAM_TEXT_LIMIT = 4000
VISION_MAX_IMAGE_BYTES = 5 * 1024 * 1024
SECRET_ENV_PREFIXES = ("ANTHROPIC_", "TELEGRAM_", "SEVENTEEN_TRACK_")
FIRST_DIGEST_WINDOW = timedelta(hours=24)
MODULE_REFRESH_SECONDS = 30
LIST_PAGE_SIZE = 5
OUT_FOR_DELIVERY_PROGRESS = 95
POLL_TICK_SECONDS = 60
NEAR_DELIVERY_PROGRESS = 80
NEAR_DELIVERY_CHECK_INTERVAL = timedelta(minutes=3)
IN_TRANSIT_CHECK_INTERVAL = timedelta(minutes=10)
RECHECK_COOLDOWN = timedelta(minutes=2)
