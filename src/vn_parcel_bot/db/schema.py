from pathlib import Path

import aiosqlite

SCHEMA_VERSION = 4

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
    """
BEGIN;
CREATE TABLE parcels_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
  carrier TEXT,
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
INSERT INTO parcels_new (id, user_id, carrier, candidates, tracking_number, phone_last4, label,
  state, last_status_text, last_event_at, consecutive_failures, next_check_at, delivered_at,
  created_at, updated_at)
SELECT id, user_id, carrier, candidates, tracking_number, phone_last4, label,
  state, last_status_text, last_event_at, consecutive_failures, next_check_at, delivered_at,
  created_at, updated_at FROM parcels;
DELETE FROM sqlite_sequence WHERE name = 'parcels_new';
INSERT INTO sqlite_sequence (name, seq) SELECT 'parcels_new', seq FROM sqlite_sequence
  WHERE name = 'parcels';
DROP TABLE parcels;
ALTER TABLE parcels_new RENAME TO parcels;
CREATE INDEX idx_parcels_due ON parcels (state, next_check_at);
COMMIT;
""",
    """
ALTER TABLE parcels ADD COLUMN progress INTEGER
  CHECK (progress IS NULL OR progress BETWEEN 0 AND 100);
""",
    """
ALTER TABLE users ADD COLUMN home_lat REAL;
ALTER TABLE users ADD COLUMN home_lon REAL;
ALTER TABLE parcels ADD COLUMN place TEXT;
CREATE TABLE places (
  name TEXT PRIMARY KEY,
  lat REAL,
  lon REAL,
  source TEXT NOT NULL CHECK (source IN ('osm', 'province', 'none')),
  looked_up_at TEXT NOT NULL
);
""",
]


def backup_target(db_path: Path, version: int) -> Path | None:
    if str(db_path) == ":memory:":
        return None
    target = db_path.with_name(f"{db_path.name}.bak-v{version}")
    return None if target.exists() else target


async def migrate(conn: aiosqlite.Connection, db_path: Path | None = None) -> None:
    async with conn.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    current = row[0] if row else 0
    if 0 < current < SCHEMA_VERSION and db_path is not None:
        target = backup_target(db_path, current)
        if target is not None:
            await conn.execute("VACUUM INTO ?", (str(target),))
    for version in range(current, SCHEMA_VERSION):
        await conn.commit()
        await conn.execute("PRAGMA foreign_keys=OFF")
        try:
            await conn.executescript(MIGRATIONS[version])
            async with conn.execute("PRAGMA foreign_key_check") as cursor:
                if await cursor.fetchall():
                    raise RuntimeError(f"foreign key check failed after migration {version + 1}")
            await conn.execute(f"PRAGMA user_version = {version + 1}")
            await conn.commit()
        finally:
            await conn.execute("PRAGMA foreign_keys=ON")
