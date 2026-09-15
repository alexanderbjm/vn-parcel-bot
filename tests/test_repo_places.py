from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.db.schema import MIGRATIONS, SCHEMA_VERSION

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)


@pytest.fixture
async def repo(tmp_path):
    opened = await Repository.open(tmp_path / "bot.sqlite3")
    yield opened
    await opened.close()


async def test_home_location_is_rounded_and_cleared(repo):
    await repo.upsert_user(1, now=T0, is_allowed=True)
    await repo.set_home(1, 21.02851, 105.85422)
    user = await repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (21.03, 105.85)
    await repo.clear_home(1)
    user = await repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (None, None)


async def test_parcel_place_and_places_cache(repo):
    await repo.upsert_user(1, now=T0, is_allowed=True)
    parcel = await repo.add_parcel(
        user_id=1,
        carrier="spx",
        candidates=("spx",),
        tracking_number="SPXVN000000000001",
        phone_last4=None,
        now=T0,
        next_check_at=T0,
    )
    assert parcel.place is None
    await repo.set_place(parcel.id, "21-HNI Thanh Tri 2 Hub")
    assert (await repo.get_parcel(parcel.id)).place == "21-HNI Thanh Tri 2 Hub"
    assert await repo.get_place("HNI|Thanh Tri") is None
    await repo.save_place("HNI|Thanh Tri", 20.94, 105.84, "osm", T0)
    await repo.save_place("HNI|Thanh Tri", None, None, "none", T0 + timedelta(days=1))
    row = await repo.get_place("HNI|Thanh Tri")
    assert (row.lat, row.lon, row.source) == (None, None, "none")
    assert row.looked_up_at == T0 + timedelta(days=1)


async def test_migration_from_v3_keeps_rows_and_writes_a_backup(tmp_path):
    path = tmp_path / "old.sqlite3"
    async with aiosqlite.connect(path) as conn:
        for script in MIGRATIONS[:3]:
            await conn.executescript(script)
        await conn.execute("PRAGMA user_version = 3")
        await conn.execute(
            "INSERT INTO users (telegram_id, is_allowed, created_at) VALUES (1, 1, ?)",
            (T0.isoformat(),),
        )
        await conn.commit()
    migrated = await Repository.open(path)
    try:
        assert SCHEMA_VERSION == 4
        assert (await migrated.get_user(1)).home_lat is None
        assert path.with_name("old.sqlite3.bak-v3").exists()
    finally:
        await migrated.close()
