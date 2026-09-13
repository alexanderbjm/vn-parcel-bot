import aiosqlite

SCHEMA_VERSION = 1

MIGRATIONS: list[str] = [
    """
CREATE TABLE users (
  telegram_id INTEGER PRIMARY KEY,
  name TEXT,
  default_phone_last4 TEXT
    CHECK (default_phone_last4 IS NULL OR default_phone_last4 GLOB '[0-9][0-9][0-9][0-9]'),
  is_admin INTEGER NOT NULL DEFAULT 0,
  is_allowed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE parcels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  carrier TEXT CHECK (carrier IS NULL OR carrier IN (
    'spx', 'jt', 'cainiao', 'fourpx', 'ninjavan', 'ghn',
    'best', 'yunexpress', 'ghtk', 'viettelpost', 'vnpost', 'lex')),
  candidates TEXT NOT NULL CHECK (length(candidates) > 0),
  tracking_number TEXT NOT NULL,
  phone_last4 TEXT CHECK (phone_last4 IS NULL OR phone_last4 GLOB '[0-9][0-9][0-9][0-9]'),
  label TEXT,
  state TEXT NOT NULL DEFAULT 'pending'
    CHECK (state IN ('pending', 'in_transit', 'delivered', 'returned', 'expired', 'stale')),
  last_status_text TEXT,
  last_event_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  next_check_at TEXT NOT NULL,
  delivered_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (carrier IS NOT NULL OR state IN ('pending', 'expired')),
  UNIQUE (user_id, tracking_number)
);
CREATE INDEX idx_parcels_due ON parcels (state, next_check_at);

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parcel_id INTEGER NOT NULL REFERENCES parcels(id) ON DELETE CASCADE,
  event_key TEXT NOT NULL,
  event_time TEXT NOT NULL,
  description TEXT NOT NULL,
  location TEXT,
  raw_status TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (parcel_id, event_key)
);

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
""",
]


async def migrate(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    current = row[0] if row else 0
    for version in range(current, SCHEMA_VERSION):
        await conn.executescript(MIGRATIONS[version])
        await conn.execute(f"PRAGMA user_version = {version + 1}")
        await conn.commit()
