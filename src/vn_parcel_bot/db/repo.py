import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self, cast

import aiosqlite

from vn_parcel_bot.carriers.models import CarrierCode, TrackingEvent
from vn_parcel_bot.db.schema import migrate

ParcelState = Literal["pending", "in_transit", "delivered", "returned", "expired", "stale"]
ACTIVE_STATES: tuple[ParcelState, ...] = ("pending", "in_transit")
# A quiet order has still not arrived, so it keeps being checked even though the list
# and the digests no longer count it as active.
POLLED_STATES: tuple[ParcelState, ...] = (*ACTIVE_STATES, "stale")
TERMINAL_STATES: tuple[ParcelState, ...] = ("delivered", "returned", "expired", "stale")

_PARCEL_COLUMNS = (
    "id, user_id, carrier, candidates, tracking_number, phone_last4, label, state, "
    "last_status_text, last_event_at, consecutive_failures, next_check_at, delivered_at, "
    "created_at, updated_at, progress, place"
)
_P_PARCEL_COLUMNS = ", ".join(f"p.{name.strip()}" for name in _PARCEL_COLUMNS.split(","))
_USER_COLUMNS = (
    "telegram_id, name, default_phone_last4, is_admin, is_allowed, created_at, home_lat, home_lon"
)


class DuplicateParcelError(Exception):
    pass


@dataclass(frozen=True)
class User:
    telegram_id: int
    name: str | None
    default_phone_last4: str | None
    is_admin: bool
    is_allowed: bool
    created_at: datetime
    home_lat: float | None = None
    home_lon: float | None = None


@dataclass(frozen=True)
class PlaceRow:
    name: str
    lat: float | None
    lon: float | None
    source: str
    looked_up_at: datetime


@dataclass(frozen=True)
class Parcel:
    id: int
    user_id: int
    carrier: CarrierCode | None
    candidates: tuple[CarrierCode, ...]
    tracking_number: str
    phone_last4: str | None
    label: str | None
    state: ParcelState
    last_status_text: str | None
    last_event_at: datetime | None
    consecutive_failures: int
    next_check_at: datetime
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    progress: int | None = None
    place: str | None = None

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def is_polled(self) -> bool:
        return self.state in POLLED_STATES

    @property
    def is_resolved(self) -> bool:
        return self.carrier is not None

    def try_order(self) -> tuple[CarrierCode, ...]:
        return (self.carrier,) if self.carrier is not None else self.candidates


def _to_db(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetimes stored in the database must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _from_db(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _required(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _flag(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _user(row: aiosqlite.Row) -> User:
    return User(
        telegram_id=row["telegram_id"],
        name=row["name"],
        default_phone_last4=row["default_phone_last4"],
        is_admin=bool(row["is_admin"]),
        is_allowed=bool(row["is_allowed"]),
        created_at=_required(row["created_at"]),
        home_lat=row["home_lat"],
        home_lon=row["home_lon"],
    )


def _parcel(row: aiosqlite.Row) -> Parcel:
    return Parcel(
        id=row["id"],
        user_id=row["user_id"],
        carrier=row["carrier"],
        candidates=cast(tuple[CarrierCode, ...], tuple(row["candidates"].split(","))),
        tracking_number=row["tracking_number"],
        phone_last4=row["phone_last4"],
        label=row["label"],
        state=row["state"],
        last_status_text=row["last_status_text"],
        last_event_at=_from_db(row["last_event_at"]),
        consecutive_failures=row["consecutive_failures"],
        next_check_at=_required(row["next_check_at"]),
        delivered_at=_from_db(row["delivered_at"]),
        created_at=_required(row["created_at"]),
        updated_at=_required(row["updated_at"]),
        progress=row["progress"],
        place=row["place"],
    )


class Repository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @classmethod
    async def open(cls, db_path: Path | str) -> Self:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=5000")
        await migrate(conn, path)
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    async def _fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, tuple(params)) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, tuple(params)) as cursor:
            return list(await cursor.fetchall())

    async def _write(self, sql: str, params: Iterable[Any] = ()) -> int:
        async with self._conn.execute(sql, tuple(params)) as cursor:
            rowcount = cursor.rowcount
        await self._conn.commit()
        return rowcount

    # users

    async def upsert_user(
        self,
        telegram_id: int,
        *,
        now: datetime,
        name: str | None = None,
        is_allowed: bool | None = None,
        is_admin: bool | None = None,
    ) -> User:
        await self._write(
            "INSERT INTO users (telegram_id, name, is_admin, is_allowed, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET "
            "name = COALESCE(?, name), "
            "is_admin = COALESCE(?, is_admin), "
            "is_allowed = COALESCE(?, is_allowed)",
            (
                telegram_id,
                name,
                int(bool(is_admin)),
                int(bool(is_allowed)),
                _to_db(now),
                name,
                _flag(is_admin),
                _flag(is_allowed),
            ),
        )
        user = await self.get_user(telegram_id)
        assert user is not None
        return user

    async def get_user(self, telegram_id: int) -> User | None:
        row = await self._fetchone(
            f"SELECT {_USER_COLUMNS} FROM users WHERE telegram_id = ?",  # noqa: S608
            (telegram_id,),
        )
        return _user(row) if row else None

    async def list_users(self) -> list[User]:
        rows = await self._fetchall(
            f"SELECT {_USER_COLUMNS} FROM users ORDER BY telegram_id"  # noqa: S608
        )
        return [_user(row) for row in rows]

    async def set_default_phone(self, telegram_id: int, last4: str | None) -> None:
        await self._write(
            "UPDATE users SET default_phone_last4 = ? WHERE telegram_id = ?", (last4, telegram_id)
        )

    async def set_home(self, telegram_id: int, lat: float, lon: float) -> None:
        await self._write(
            "UPDATE users SET home_lat = ?, home_lon = ? WHERE telegram_id = ?",
            (round(lat, 2), round(lon, 2), telegram_id),
        )

    async def clear_home(self, telegram_id: int) -> None:
        await self._write(
            "UPDATE users SET home_lat = NULL, home_lon = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )

    # parcels

    async def add_parcel(
        self,
        *,
        user_id: int,
        carrier: CarrierCode | None,
        candidates: Sequence[CarrierCode],
        tracking_number: str,
        phone_last4: str | None,
        now: datetime,
        next_check_at: datetime,
    ) -> Parcel:
        ordered = tuple(candidates)
        if not ordered:
            raise ValueError("a parcel needs at least one candidate carrier")
        if carrier is not None and ordered != (carrier,):
            raise ValueError("a resolved parcel's candidates must be exactly its carrier")
        created = _to_db(now)
        values = (
            user_id,
            carrier,
            ",".join(ordered),
            tracking_number,
            phone_last4,
            _to_db(next_check_at),
            created,
            created,
        )
        try:
            async with self._conn.execute(
                "INSERT INTO parcels (user_id, carrier, candidates, tracking_number, phone_last4, "
                "state, next_check_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                values,
            ) as cursor:
                parcel_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            await self._conn.rollback()
            if "UNIQUE" in str(exc):
                raise DuplicateParcelError(tracking_number) from exc
            raise
        await self._conn.commit()
        parcel = await self.get_parcel(cast(int, parcel_id))
        assert parcel is not None
        return parcel

    async def get_parcel(self, parcel_id: int) -> Parcel | None:
        row = await self._fetchone(
            f"SELECT {_PARCEL_COLUMNS} FROM parcels WHERE id = ?",  # noqa: S608
            (parcel_id,),
        )
        return _parcel(row) if row else None

    async def find_parcel(self, user_id: int, tracking_number: str) -> Parcel | None:
        row = await self._fetchone(
            f"SELECT {_PARCEL_COLUMNS} FROM parcels "  # noqa: S608
            "WHERE user_id = ? AND tracking_number = ?",
            (user_id, tracking_number),
        )
        return _parcel(row) if row else None

    async def list_parcels(self, user_id: int, *, terminal_since: datetime) -> list[Parcel]:
        rows = await self._fetchall(
            f"SELECT {_PARCEL_COLUMNS} FROM parcels "  # noqa: S608
            "WHERE user_id = ? AND (state IN ('pending', 'in_transit') OR updated_at >= ?) "
            "ORDER BY created_at, id",
            (user_id, _to_db(terminal_since)),
        )
        return [_parcel(row) for row in rows]

    async def parcel_ids_with_events_since(self, user_id: int, since: datetime) -> set[int]:
        rows = await self._fetchall(
            "SELECT DISTINCT e.parcel_id FROM events e JOIN parcels p ON p.id = e.parcel_id "
            "WHERE p.user_id = ? AND e.created_at >= ?",
            (user_id, _to_db(since)),
        )
        return {int(row[0]) for row in rows}

    async def count_active_parcels(self, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) FROM parcels WHERE user_id = ? AND state IN ('pending', 'in_transit')",
            (user_id,),
        )
        return int(row[0]) if row else 0

    async def active_parcels_for_user(self, user_id: int) -> list[Parcel]:
        rows = await self._fetchall(
            f"SELECT {_PARCEL_COLUMNS} FROM parcels "  # noqa: S608
            "WHERE user_id = ? AND state IN ('pending', 'in_transit') ORDER BY created_at, id",
            (user_id,),
        )
        return [_parcel(row) for row in rows]

    async def due_parcels(self, now: datetime) -> list[Parcel]:
        rows = await self._fetchall(
            f"SELECT {_P_PARCEL_COLUMNS} FROM parcels p "  # noqa: S608
            "JOIN users u ON u.telegram_id = p.user_id "
            "WHERE u.is_allowed = 1 AND p.state IN ('pending', 'in_transit', 'stale') "
            "AND p.next_check_at <= ? ORDER BY p.next_check_at, p.id",
            (_to_db(now),),
        )
        return [_parcel(row) for row in rows]

    async def resolve_carrier(self, parcel_id: int, carrier: CarrierCode, now: datetime) -> None:
        await self._write(
            "UPDATE parcels SET carrier = ?, candidates = ?, updated_at = ? WHERE id = ?",
            (carrier, carrier, _to_db(now), parcel_id),
        )

    async def set_candidates(
        self, parcel_id: int, candidates: Sequence[CarrierCode], now: datetime
    ) -> None:
        """Replace the carriers to try; a single candidate becomes the resolved carrier."""
        ordered = tuple(candidates)
        if not ordered:
            raise ValueError("a parcel needs at least one candidate carrier")
        await self._write(
            "UPDATE parcels SET carrier = ?, candidates = ?, consecutive_failures = 0, "
            "updated_at = ? WHERE id = ?",
            (ordered[0] if len(ordered) == 1 else None, ",".join(ordered), _to_db(now), parcel_id),
        )

    async def set_label(self, parcel_id: int, label: str | None, now: datetime) -> None:
        await self._write(
            "UPDATE parcels SET label = ?, updated_at = ? WHERE id = ?",
            (label, _to_db(now), parcel_id),
        )

    async def set_place(self, parcel_id: int, place: str | None) -> None:
        await self._write("UPDATE parcels SET place = ? WHERE id = ?", (place, parcel_id))

    async def delete_parcel(self, parcel_id: int) -> None:
        await self._write("DELETE FROM parcels WHERE id = ?", (parcel_id,))

    async def record_check_success(
        self,
        parcel_id: int,
        *,
        state: ParcelState,
        last_status_text: str | None,
        last_event_at: datetime | None,
        next_check_at: datetime,
        now: datetime,
        delivered_at: datetime | None = None,
        progress: int | None = None,
        reset_progress: bool = False,
    ) -> None:
        """`reset_progress` stores the given progress as is instead of keeping the maximum."""
        await self._write(
            "UPDATE parcels SET state = ?, "
            "last_status_text = COALESCE(?, last_status_text), "
            "last_event_at = COALESCE(?, last_event_at), "
            "delivered_at = COALESCE(?, delivered_at), "
            "progress = CASE WHEN ? THEN ? WHEN ? IS NULL THEN progress "
            "ELSE MAX(COALESCE(progress, 0), ?) END, "
            "consecutive_failures = 0, next_check_at = ?, updated_at = ? WHERE id = ?",
            (
                state,
                last_status_text,
                _to_db(last_event_at) if last_event_at else None,
                _to_db(delivered_at) if delivered_at else None,
                int(reset_progress),
                progress,
                progress,
                progress,
                _to_db(next_check_at),
                _to_db(now),
                parcel_id,
            ),
        )

    async def record_check_failure(
        self, parcel_id: int, *, next_check_at: datetime, now: datetime
    ) -> int:
        async with self._conn.execute(
            "UPDATE parcels SET consecutive_failures = consecutive_failures + 1, "
            "next_check_at = ?, updated_at = ? WHERE id = ? RETURNING consecutive_failures",
            (_to_db(next_check_at), _to_db(now), parcel_id),
        ) as cursor:
            row = await cursor.fetchone()
        await self._conn.commit()
        return int(row[0]) if row else 0

    async def set_state(self, parcel_id: int, state: ParcelState, now: datetime) -> None:
        await self._write(
            "UPDATE parcels SET state = ?, updated_at = ? WHERE id = ?",
            (state, _to_db(now), parcel_id),
        )

    async def delete_terminal_before(self, cutoff: datetime) -> int:
        return await self._write(
            "DELETE FROM parcels "
            "WHERE state IN ('delivered', 'returned', 'expired', 'stale') AND updated_at < ?",
            (_to_db(cutoff),),
        )

    async def count_all_active(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) FROM parcels WHERE state IN ('pending', 'in_transit')"
        )
        return int(row[0]) if row else 0

    # events

    async def insert_events(
        self, parcel_id: int, events: Sequence[TrackingEvent], now: datetime
    ) -> list[TrackingEvent]:
        created = _to_db(now)
        inserted: list[TrackingEvent] = []
        for event in sorted(events, key=lambda e: e.time):
            async with self._conn.execute(
                "INSERT OR IGNORE INTO events "
                "(parcel_id, event_key, event_time, description, location, raw_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    parcel_id,
                    event.key,
                    _to_db(event.time),
                    event.description,
                    event.location,
                    event.raw_status,
                    created,
                ),
            ) as cursor:
                if cursor.rowcount == 1:
                    inserted.append(event)
        await self._conn.commit()
        return inserted

    async def replace_events(
        self, parcel_id: int, events: Sequence[TrackingEvent], now: datetime
    ) -> None:
        """Swap a parcel's stored history for a fresh read in one transaction."""
        created = _to_db(now)
        try:
            await self._conn.execute("DELETE FROM events WHERE parcel_id = ?", (parcel_id,))
            for event in sorted(events, key=lambda e: e.time):
                await self._conn.execute(
                    "INSERT OR IGNORE INTO events "
                    "(parcel_id, event_key, event_time, description, location, raw_status, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        parcel_id,
                        event.key,
                        _to_db(event.time),
                        event.description,
                        event.location,
                        event.raw_status,
                        created,
                    ),
                )
        except BaseException:
            await self._conn.rollback()
            raise
        await self._conn.commit()

    async def event_keys(self, parcel_id: int) -> set[str]:
        rows = await self._fetchall(
            "SELECT event_key FROM events WHERE parcel_id = ?", (parcel_id,)
        )
        return {row["event_key"] for row in rows}

    async def reset_failures(self, parcel_ids: Sequence[int]) -> None:
        if not parcel_ids:
            return
        marks = ", ".join("?" for _ in parcel_ids)
        await self._write(
            f"UPDATE parcels SET consecutive_failures = 0 WHERE id IN ({marks})",  # noqa: S608
            parcel_ids,
        )

    async def list_events(self, parcel_id: int, limit: int) -> list[TrackingEvent]:
        rows = await self._fetchall(
            "SELECT event_time, description, location, raw_status FROM events "
            "WHERE parcel_id = ? ORDER BY event_time DESC, id DESC LIMIT ?",
            (parcel_id, limit),
        )
        return [
            TrackingEvent(
                time=_required(row["event_time"]),
                description=row["description"],
                location=row["location"],
                raw_status=row["raw_status"],
            )
            for row in reversed(rows)
        ]

    async def count_events(self, parcel_id: int) -> int:
        row = await self._fetchone("SELECT COUNT(*) FROM events WHERE parcel_id = ?", (parcel_id,))
        return int(row[0]) if row else 0

    # meta

    # places

    async def get_place(self, name: str) -> PlaceRow | None:
        row = await self._fetchone(
            "SELECT name, lat, lon, source, looked_up_at FROM places WHERE name = ?", (name,)
        )
        if row is None:
            return None
        return PlaceRow(
            row["name"], row["lat"], row["lon"], row["source"], _required(row["looked_up_at"])
        )

    async def save_place(
        self, name: str, lat: float | None, lon: float | None, source: str, now: datetime
    ) -> None:
        await self._write(
            "INSERT INTO places (name, lat, lon, source, looked_up_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET lat = excluded.lat, lon = excluded.lon, "
            "source = excluded.source, looked_up_at = excluded.looked_up_at",
            (name, lat, lon, source, _to_db(now)),
        )

    async def get_meta(self, key: str) -> str | None:
        row = await self._fetchone("SELECT value FROM meta WHERE key = ?", (key,))
        return row[0] if row else None

    async def delete_meta(self, key: str) -> None:
        await self._write("DELETE FROM meta WHERE key = ?", (key,))

    async def set_meta(self, key: str, value: str) -> None:
        await self._write(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
