from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeClock, FakeNotifier, ev
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.digest import DIGEST_META_PREFIX, DigestService

T0 = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)  # 07:00 in Asia/Ho_Chi_Minh


@pytest.fixture
async def repo(tmp_path):
    r = await Repository.open(tmp_path / "digest.sqlite3")
    yield r
    await r.close()


@pytest.fixture
def clock():
    return FakeClock(T0)


async def allowed_user(repo, telegram_id=1):
    return await repo.upsert_user(
        telegram_id, now=T0 - timedelta(days=3), name="A", is_allowed=True
    )


async def add_parcel(
    repo, user_id, code, *, state="pending", label=None, updated=None, event_at=None
):
    created = T0 - timedelta(days=2)
    parcel = await repo.add_parcel(
        user_id=user_id,
        carrier="spx",
        candidates=("spx",),
        tracking_number=code,
        phone_last4=None,
        now=created,
        next_check_at=created + timedelta(minutes=20),
    )
    if label:
        await repo.set_label(parcel.id, label, created)
    touched = updated or created
    moving = state != "pending"
    await repo.record_check_success(
        parcel.id,
        state=state,
        last_status_text="Đang giao hàng" if moving else None,
        last_event_at=touched if moving else None,
        next_check_at=touched + timedelta(minutes=20),
        now=touched,
        delivered_at=touched if state == "delivered" else None,
    )
    if event_at is not None:
        await repo.insert_events(parcel.id, [ev(0, base=event_at)], event_at)
    return await repo.get_parcel(parcel.id)


async def test_build_returns_none_without_parcels(repo, settings, clock):
    await allowed_user(repo)
    assert await DigestService(repo, FakeNotifier(), settings, clock).build(1, T0) is None


async def test_first_digest_lists_parcels_and_marks_recent_events(repo, settings, clock):
    await allowed_user(repo)
    await add_parcel(repo, 1, "SPXVN000000000001", label="Ốp lưng", event_at=T0 - timedelta(days=2))
    await add_parcel(
        repo,
        1,
        "SPXVN000000000002",
        state="in_transit",
        label="Tai nghe",
        updated=T0 - timedelta(hours=1),
        event_at=T0 - timedelta(hours=1),
    )
    text = await DigestService(repo, FakeNotifier(), settings, clock).build(1, T0)
    assert text.startswith("🗓 <b>Tóm tắt đơn hàng</b> · 07:00")
    lines = text.splitlines()
    old_line = next(line for line in lines if "Ốp lưng" in line)
    new_line = next(line for line in lines if "Tai nghe" in line)
    assert "🆕" not in old_line
    assert new_line.endswith("🆕")
    assert text.endswith("Đang theo dõi 2 đơn")


async def test_finished_parcel_is_shown_once(repo, settings, clock):
    await allowed_user(repo)
    await add_parcel(
        repo,
        1,
        "SPXVN000000000003",
        state="delivered",
        label="Sạc",
        updated=T0 - timedelta(hours=2),
    )
    notifier = FakeNotifier()
    digests = DigestService(repo, notifier, settings, clock)
    assert await digests.send_all() == 1
    text = notifier.sent[0][1]
    assert "Sạc" in text
    assert "🆕" in text
    assert text.endswith("Đang theo dõi 0 đơn · 1 đơn vừa kết thúc")
    clock.advance(timedelta(hours=5))
    assert await digests.build(1, clock()) is None


async def test_event_saved_while_sending_is_marked_next_time(repo, settings, clock):
    await allowed_user(repo)
    parcel = await add_parcel(repo, 1, "SPXVN000000000004", event_at=T0 - timedelta(days=2))

    class SlowNotifier(FakeNotifier):
        async def send(self, chat_id, text, *, silent=False, reply_markup=None):
            await super().send(chat_id, text, silent=silent)
            clock.advance(timedelta(seconds=30))
            await repo.insert_events(parcel.id, [ev(0, "Đã đến kho", base=clock())], clock())
            clock.advance(timedelta(seconds=30))

    digests = DigestService(repo, SlowNotifier(), settings, clock)
    assert await digests.send_all() == 1
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}1") == T0.isoformat()
    clock.advance(timedelta(hours=5))
    assert "🆕" in await digests.build(1, clock())


async def test_failed_send_keeps_previous_since(repo, settings, clock):
    await allowed_user(repo)
    await add_parcel(repo, 1, "SPXVN000000000005")
    notifier = FakeNotifier(fail_with=RuntimeError("telegram down"))
    assert await DigestService(repo, notifier, settings, clock).send_all() == 0
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}1") is None


async def test_send_all_only_allowed_users_with_something_to_show(repo, settings, clock):
    await allowed_user(repo, 1)
    await allowed_user(repo, 2)
    await repo.upsert_user(3, now=T0, name="C", is_allowed=False)
    await add_parcel(repo, 1, "SPXVN000000000006")
    await add_parcel(repo, 3, "SPXVN000000000007")
    notifier = FakeNotifier()
    assert await DigestService(repo, notifier, settings, clock).send_all() == 1
    assert [(chat_id, silent) for chat_id, _, silent in notifier.sent] == [(1, False)]
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}1") == T0.isoformat()
    assert await repo.get_meta(f"{DIGEST_META_PREFIX}2") is None


async def test_parcel_ids_with_events_since(repo):
    await allowed_user(repo, 1)
    await allowed_user(repo, 2)
    await add_parcel(repo, 1, "SPXVN000000000008", event_at=T0 - timedelta(days=2))
    recent = await add_parcel(repo, 1, "SPXVN000000000009", event_at=T0)
    await add_parcel(repo, 2, "SPXVN000000000010", event_at=T0)
    assert await repo.parcel_ids_with_events_since(1, T0 - timedelta(hours=1)) == {recent.id}
