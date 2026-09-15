import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.fakes import ev
from vn_parcel_bot.db.repo import DuplicateParcelError, Repository
from vn_parcel_bot.db.schema import MIGRATIONS

T0 = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)


@pytest.fixture
async def repo(tmp_path):
    r = await Repository.open(tmp_path / "t.sqlite3")
    yield r
    await r.close()


async def make_user(repo, uid=1, *, allowed=True, name=None):
    return await repo.upsert_user(uid, now=T0, name=name or f"U{uid}", is_allowed=allowed)


async def add(
    repo,
    user_id=1,
    code="SPXVN000000000001",
    carrier="spx",
    candidates=None,
    *,
    phone_last4=None,
    now=T0,
    next_check_at=None,
):
    if candidates is None:
        candidates = (carrier,)
    return await repo.add_parcel(
        user_id=user_id,
        carrier=carrier,
        candidates=candidates,
        tracking_number=code,
        phone_last4=phone_last4,
        now=now,
        next_check_at=next_check_at or now,
    )


async def test_reset_failures_clears_only_the_given_parcels(repo):
    await make_user(repo)
    codes = ("SPXVN000000000001", "SPXVN000000000002", "SPXVN000000000003")
    parcels = [await add(repo, code=code) for code in codes]
    for parcel in parcels:
        await repo.record_check_failure(parcel.id, next_check_at=T0, now=T0)
    await repo.reset_failures([parcels[0].id, parcels[1].id])
    await repo.reset_failures([])
    failures = [(await repo.get_parcel(parcel.id)).consecutive_failures for parcel in parcels]
    assert failures == [0, 0, 1]


async def test_migrate_sets_user_version_and_is_idempotent(tmp_path):
    path = tmp_path / "db" / "t.sqlite3"
    first = await Repository.open(path)
    await first.close()
    second = await Repository.open(path)
    async with second._conn.execute("PRAGMA user_version") as cursor:
        assert (await cursor.fetchone())[0] == 4
    await second.close()


async def test_foreign_keys_enabled(repo):
    async with repo._conn.execute("PRAGMA foreign_keys") as cursor:
        assert (await cursor.fetchone())[0] == 1


async def test_upsert_user_insert_then_partial_update(repo):
    created = await repo.upsert_user(5, now=T0, name="A")
    assert (created.name, created.is_allowed, created.is_admin) == ("A", False, False)
    updated = await repo.upsert_user(5, now=T0 + timedelta(days=1), is_allowed=True)
    assert updated.name == "A"
    assert updated.is_allowed is True
    assert updated.created_at == T0
    assert await repo.get_user(99) is None
    assert [u.telegram_id for u in await repo.list_users()] == [5]


async def test_set_default_phone_and_clear(repo):
    await make_user(repo)
    await repo.set_default_phone(1, "1234")
    assert (await repo.get_user(1)).default_phone_last4 == "1234"
    await repo.set_default_phone(1, None)
    assert (await repo.get_user(1)).default_phone_last4 is None


async def test_default_phone_check_constraint(repo):
    await make_user(repo)
    with pytest.raises(sqlite3.IntegrityError):
        await repo._conn.execute("UPDATE users SET default_phone_last4='12a4' WHERE telegram_id=1")


async def test_add_parcel_and_get(repo):
    await make_user(repo)
    parcel = await add(repo, phone_last4=None, next_check_at=T0 + timedelta(minutes=20))
    fetched = await repo.get_parcel(parcel.id)
    assert fetched == parcel
    assert parcel.state == "pending"
    assert parcel.carrier == "spx"
    assert parcel.candidates == ("spx",)
    assert parcel.is_resolved
    assert parcel.is_active
    assert parcel.try_order() == ("spx",)
    assert parcel.next_check_at == T0 + timedelta(minutes=20)
    assert parcel.created_at.tzinfo is not None
    assert parcel.created_at == T0
    assert await repo.find_parcel(1, "SPXVN000000000001") == parcel
    assert await repo.find_parcel(1, "SPXVN000000000009") is None


async def test_add_unresolved_parcel(repo):
    await make_user(repo)
    parcel = await add(
        repo, code="GA0000000001", carrier=None, candidates=("ghn", "ninjavan"), phone_last4="1111"
    )
    assert parcel.carrier is None
    assert parcel.is_resolved is False
    assert parcel.try_order() == ("ghn", "ninjavan")
    assert parcel.phone_last4 == "1111"


async def test_add_parcel_validates_candidates(repo):
    await make_user(repo)
    with pytest.raises(ValueError):
        await add(repo, carrier=None, candidates=())
    with pytest.raises(ValueError):
        await add(repo, carrier="spx", candidates=("spx", "jt"))


async def test_unresolved_cannot_be_in_transit(repo):
    await make_user(repo)
    parcel = await add(repo, code="GA0000000001", carrier=None, candidates=("ghn", "ninjavan"))
    with pytest.raises(sqlite3.IntegrityError):
        await repo._conn.execute("UPDATE parcels SET state='in_transit' WHERE id=?", (parcel.id,))


async def test_carrier_accepts_any_module_code(repo):
    await make_user(repo)
    parcel = await add(repo)
    await repo._conn.execute("UPDATE parcels SET carrier='newcarrier' WHERE id=?", (parcel.id,))
    await repo._conn.commit()
    assert (await repo.get_parcel(parcel.id)).carrier == "newcarrier"


async def test_add_parcel_duplicate_raises_even_with_other_carrier(repo):
    await make_user(repo)
    await add(repo, code="841000072647", carrier="jt")
    with pytest.raises(DuplicateParcelError):
        await add(repo, code="841000072647", carrier="spx")


async def test_same_code_different_users_allowed(repo):
    await make_user(repo, 1)
    await make_user(repo, 2)
    a = await add(repo, user_id=1)
    b = await add(repo, user_id=2)
    assert a.id != b.id


async def test_resolve_carrier(repo):
    await make_user(repo)
    parcel = await add(repo, code="GA0000000001", carrier=None, candidates=("ghn", "ninjavan"))
    await repo.resolve_carrier(parcel.id, "ninjavan", T0 + timedelta(hours=1))
    resolved = await repo.get_parcel(parcel.id)
    assert resolved.carrier == "ninjavan"
    assert resolved.candidates == ("ninjavan",)
    assert resolved.updated_at == T0 + timedelta(hours=1)


async def test_list_parcels_includes_recent_terminal_only(repo):
    await make_user(repo)
    now = T0 + timedelta(days=10)
    a = await add(repo, code="SPXVN000000000001", now=T0)
    b = await add(repo, code="SPXVN000000000002", now=T0 + timedelta(minutes=1))
    c = await add(repo, code="SPXVN000000000003", now=T0 + timedelta(minutes=2))
    await repo.set_state(b.id, "delivered", now - timedelta(days=1))
    await repo.set_state(c.id, "delivered", now - timedelta(days=5))
    listed = await repo.list_parcels(1, terminal_since=now - timedelta(days=3))
    assert [p.id for p in listed] == [a.id, b.id]


async def test_count_active_parcels(repo):
    await make_user(repo)
    a = await add(repo, code="SPXVN000000000001")
    await add(repo, code="SPXVN000000000002")
    await repo.set_state(a.id, "delivered", T0)
    assert await repo.count_active_parcels(1) == 1
    assert await repo.count_all_active() == 1
    assert [p.tracking_number for p in await repo.active_parcels_for_user(1)] == [
        "SPXVN000000000002"
    ]


async def test_due_parcels_filters_state_time_and_allowed(repo):
    await make_user(repo, 1)
    await make_user(repo, 2, allowed=False)
    due = await add(repo, code="SPXVN000000000001", next_check_at=T0 - timedelta(minutes=1))
    earlier = await add(repo, code="SPXVN000000000002", next_check_at=T0 - timedelta(minutes=10))
    await add(repo, code="SPXVN000000000003", next_check_at=T0 + timedelta(hours=1))
    delivered = await add(repo, code="SPXVN000000000004", next_check_at=T0 - timedelta(hours=1))
    await repo.set_state(delivered.id, "delivered", T0)
    await add(repo, user_id=2, code="SPXVN000000000005", next_check_at=T0 - timedelta(hours=2))
    assert [p.id for p in await repo.due_parcels(T0)] == [earlier.id, due.id]


async def test_insert_events_returns_only_new_ascending(repo):
    await make_user(repo)
    parcel = await add(repo)
    e1, e2, e3 = ev(0, "A"), ev(10, "B"), ev(20, "C")
    assert await repo.insert_events(parcel.id, [e2, e1], T0) == [e1, e2]
    assert await repo.insert_events(parcel.id, [e1, e2, e3], T0) == [e3]
    assert await repo.insert_events(parcel.id, [e1, e2, e3], T0) == []
    assert await repo.count_events(parcel.id) == 3


async def test_list_events_limit_returns_most_recent_ascending(repo):
    await make_user(repo)
    parcel = await add(repo)
    events = [ev(i, f"E{i}", None if i % 2 else "Kho") for i in range(5)]
    await repo.insert_events(parcel.id, events, T0)
    listed = await repo.list_events(parcel.id, 3)
    assert listed == events[2:]
    assert listed[1].location is None


async def test_delete_parcel_cascades_events(repo):
    await make_user(repo)
    parcel = await add(repo)
    await repo.insert_events(parcel.id, [ev(0), ev(1)], T0)
    await repo.delete_parcel(parcel.id)
    assert await repo.get_parcel(parcel.id) is None
    assert await repo.count_events(parcel.id) == 0


async def test_record_check_success_resets_failures_and_keeps_nulls(repo):
    await make_user(repo)
    parcel = await add(repo)
    await repo.record_check_success(
        parcel.id,
        state="in_transit",
        last_status_text="Đang giao",
        last_event_at=T0,
        next_check_at=T0 + timedelta(minutes=20),
        now=T0,
    )
    await repo.record_check_failure(parcel.id, next_check_at=T0, now=T0)
    await repo.record_check_failure(parcel.id, next_check_at=T0, now=T0)
    await repo.record_check_success(
        parcel.id,
        state="delivered",
        last_status_text=None,
        last_event_at=None,
        next_check_at=T0 + timedelta(hours=1),
        now=T0 + timedelta(hours=1),
        delivered_at=T0 + timedelta(minutes=30),
    )
    refreshed = await repo.get_parcel(parcel.id)
    assert refreshed.consecutive_failures == 0
    assert refreshed.last_status_text == "Đang giao"
    assert refreshed.last_event_at == T0
    assert refreshed.state == "delivered"
    assert refreshed.delivered_at == T0 + timedelta(minutes=30)
    assert refreshed.is_active is False


async def test_record_check_failure_increments_and_returns(repo):
    await make_user(repo)
    parcel = await add(repo)
    assert (
        await repo.record_check_failure(parcel.id, next_check_at=T0 + timedelta(minutes=40), now=T0)
        == 1
    )
    assert (
        await repo.record_check_failure(parcel.id, next_check_at=T0 + timedelta(minutes=80), now=T0)
        == 2
    )
    assert (await repo.get_parcel(parcel.id)).next_check_at == T0 + timedelta(minutes=80)


async def test_set_label_and_clear(repo):
    await make_user(repo)
    parcel = await add(repo)
    await repo.set_label(parcel.id, "Áo khoác", T0)
    assert (await repo.get_parcel(parcel.id)).label == "Áo khoác"
    await repo.set_label(parcel.id, None, T0)
    assert (await repo.get_parcel(parcel.id)).label is None


async def test_delete_terminal_before(repo):
    await make_user(repo)
    old = await add(repo, code="SPXVN000000000001")
    recent = await add(repo, code="SPXVN000000000002")
    active = await add(repo, code="SPXVN000000000003")
    await repo.set_state(old.id, "delivered", T0 - timedelta(days=40))
    await repo.set_state(recent.id, "expired", T0 - timedelta(days=5))
    assert await repo.delete_terminal_before(T0 - timedelta(days=30)) == 1
    assert await repo.get_parcel(old.id) is None
    assert await repo.get_parcel(recent.id) is not None
    assert await repo.get_parcel(active.id) is not None


async def test_meta_roundtrip_and_overwrite(repo):
    assert await repo.get_meta("k") is None
    await repo.set_meta("k", "1")
    await repo.set_meta("k", "2")
    assert await repo.get_meta("k") == "2"


async def test_naive_datetime_rejected(repo):
    await make_user(repo)
    with pytest.raises(ValueError):
        await add(repo, now=datetime(2026, 9, 1), next_check_at=T0)


def make_v1_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0])
    conn.execute("PRAGMA user_version = 1")
    conn.execute(
        "INSERT INTO users (telegram_id, name, is_admin, is_allowed, created_at) "
        "VALUES (1, 'A', 0, 1, '2026-09-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO parcels (id, user_id, carrier, candidates, tracking_number, state, "
        "next_check_at, created_at, updated_at) VALUES (7, 1, 'cainiao', 'cainiao', "
        "'LP00000000000001', 'in_transit', '2026-09-01T00:20:00+00:00', "
        "'2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO events (parcel_id, event_key, event_time, description, created_at) "
        "VALUES (7, 'k1', '2026-09-01T00:05:00+00:00', 'Picked up', '2026-09-01T00:06:00+00:00')"
    )
    conn.commit()
    conn.close()


async def test_migration_2_keeps_rows_and_events(tmp_path):
    path = tmp_path / "old.sqlite3"
    await asyncio.to_thread(make_v1_database, path)
    repo = await Repository.open(path)
    try:
        async with repo._conn.execute("PRAGMA user_version") as cursor:
            assert (await cursor.fetchone())[0] == 4
        parcel = await repo.get_parcel(7)
        assert (parcel.carrier, parcel.tracking_number, parcel.state) == (
            "cainiao",
            "LP00000000000001",
            "in_transit",
        )
        assert [event.description for event in await repo.list_events(7, 10)] == ["Picked up"]
        added = await repo.add_parcel(
            user_id=1,
            carrier="sf",
            candidates=("sf",),
            tracking_number="SF0000000000001",
            phone_last4=None,
            now=T0,
            next_check_at=T0,
        )
        assert added.id == 8
        async with repo._conn.execute("PRAGMA foreign_keys") as cursor:
            assert (await cursor.fetchone())[0] == 1
    finally:
        await repo.close()
    assert await asyncio.to_thread((tmp_path / "old.sqlite3.bak-v1").exists)


async def test_backup_is_not_overwritten(tmp_path):
    path = tmp_path / "old.sqlite3"
    await asyncio.to_thread(make_v1_database, path)
    backup = tmp_path / "old.sqlite3.bak-v1"
    await asyncio.to_thread(backup.write_bytes, b"keep")
    repo = await Repository.open(path)
    await repo.close()
    assert await asyncio.to_thread(backup.read_bytes) == b"keep"


async def test_fresh_database_has_no_backup(tmp_path):
    repo = await Repository.open(tmp_path / "new.sqlite3")
    await repo.close()
    assert not await asyncio.to_thread((tmp_path / "new.sqlite3.bak-v1").exists)


async def test_progress_only_moves_forward(repo):
    await make_user(repo)
    parcel = await add(repo)

    async def record(value):
        await repo.record_check_success(
            parcel.id,
            state="in_transit",
            last_status_text=None,
            last_event_at=None,
            next_check_at=T0,
            now=T0,
            progress=value,
        )
        return (await repo.get_parcel(parcel.id)).progress

    assert parcel.progress is None
    assert await record(50) == 50
    assert await record(30) == 50
    assert await record(None) == 50
    assert await record(95) == 95


async def test_delete_meta(repo):
    await repo.set_meta("sticker:spx", "file-1")
    await repo.delete_meta("sticker:spx")
    assert await repo.get_meta("sticker:spx") is None
    await repo.delete_meta("missing")
