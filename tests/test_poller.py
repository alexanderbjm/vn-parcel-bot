import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeCarrier, FakeClock, FakeNotifier, ev, fake_registry, found
from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent
from vn_parcel_bot.constants import MAX_CHECK_GAP
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.poller import FetchKey, Poller, fetch_keys

T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)
ADMIN = 111
USER = 2
SPX = "SPXVN000000000001"
JT = "840000000001"
GEN = "GA0000000001"


@pytest.fixture
async def repo(tmp_path):
    r = await Repository.open(tmp_path / "t.sqlite3")
    await r.upsert_user(ADMIN, now=T0, name="Admin", is_allowed=True, is_admin=True)
    await r.upsert_user(USER, now=T0, name="Member", is_allowed=True)
    yield r
    await r.close()


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def fakes():
    return {code: FakeCarrier(code) for code in ("spx", "jt", "ghn", "ninjavan")}


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def sleeps():
    return []


def make_poller(repo, fakes, notifier, settings, clock, sleeps):
    async def fake_sleep(seconds):
        sleeps.append(seconds)

    return Poller(
        repo, fake_registry(fakes), None, notifier, settings, clock, fake_sleep, lambda: 0.5
    )


@pytest.fixture
def poller(repo, fakes, notifier, settings, clock, sleeps):
    return make_poller(repo, fakes, notifier, settings, clock, sleeps)


async def add(
    repo,
    code,
    carrier,
    *,
    user_id=USER,
    candidates=None,
    last4=None,
    due=True,
    created=T0,
):
    return await repo.add_parcel(
        user_id=user_id,
        carrier=carrier,
        candidates=candidates or (carrier,),
        tracking_number=code,
        phone_last4=last4,
        now=created,
        next_check_at=T0 if due else T0 + timedelta(hours=1),
    )


def messages_to(notifier, chat_id):
    return [text for cid, text, _ in notifier.sent if cid == chat_id]


async def test_fetch_keys(repo, fakes):
    jt = await add(repo, JT, "jt", last4="1111")
    spx = await add(repo, SPX, "spx")
    bare = await add(repo, GEN, None, candidates=("ghn", "ninjavan"))
    phoned = await add(repo, "GA0000000002", None, candidates=("ghn", "ninjavan"), last4="2222")
    unmapped = await add(repo, "LP00000000000001", "cainiao")
    assert fetch_keys(jt, fake_registry(fakes).current) == [FetchKey("jt", JT, "1111")]
    assert fetch_keys(spx, fake_registry(fakes).current) == [FetchKey("spx", SPX, None)]
    assert fetch_keys(bare, fake_registry(fakes).current) == [FetchKey("ninjavan", GEN, None)]
    assert fetch_keys(phoned, fake_registry(fakes).current) == [
        FetchKey("ghn", "GA0000000002", "2222"),
        FetchKey("ninjavan", "GA0000000002", None),
    ]
    assert fetch_keys(unmapped, fake_registry(fakes).current) == []


async def test_fetch_keys_falls_back_to_the_owners_saved_digits(repo, fakes):
    bare = await add(repo, GEN, None, candidates=("ghn", "ninjavan"))
    snapshot = fake_registry(fakes).current
    assert fetch_keys(bare, snapshot) == [FetchKey("ninjavan", GEN, None)]
    assert fetch_keys(bare, snapshot, "7777") == [
        FetchKey("ghn", GEN, "7777"),
        FetchKey("ninjavan", GEN, None),
    ]


async def test_a_parcel_with_no_digits_polls_once_the_owner_saves_them(poller, repo, fakes):
    # A carrier whose only candidate needs the recipient's digits yields no fetch key at all,
    # so the parcel would sit in /list pending forever without the fallback.
    await add(repo, JT, "jt", last4=None)
    await poller.run_cycle()
    assert fakes["jt"].calls == []

    await repo.set_default_phone(USER, "7777")
    await poller.run_cycle()
    assert fakes["jt"].calls == [(JT, "7777")]


async def test_a_stored_parcel_digit_wins_over_the_saved_default(poller, repo, fakes):
    await add(repo, JT, "jt", last4="2222")
    await repo.set_default_phone(USER, "7777")
    await poller.run_cycle()
    assert fakes["jt"].calls == [(JT, "2222")]


async def test_no_due_parcels(poller, notifier):
    report = await poller.run_cycle()
    assert (report.parcels_checked, report.fetches, report.new_events, report.messages_sent) == (
        0,
        0,
        0,
        0,
    )
    assert report.skipped is False
    assert notifier.sent == []


async def test_skips_not_yet_due(poller, repo, fakes):
    await add(repo, SPX, "spx", due=False)
    await poller.run_cycle()
    assert fakes["spx"].calls == []


async def test_new_events_notify_once(poller, repo, fakes, notifier, clock):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), ev(10, "Beta"))
    report = await poller.run_cycle()
    sent = messages_to(notifier, USER)
    assert len(sent) == 1
    assert "Beta" in sent[0], "the newest scan"
    assert "Alpha" not in sent[0], "older scans stay in the history, not the message"
    assert (await repo.get_parcel(parcel.id)).state == "in_transit"
    assert (report.parcels_checked, report.fetches, report.new_events, report.messages_sent) == (
        1,
        1,
        2,
        1,
    )
    clock.advance(timedelta(minutes=20))
    await poller.run_cycle()
    assert len(fakes["spx"].calls) == 2
    assert len(notifier.sent) == 1


async def test_only_new_events_in_second_message(poller, repo, fakes, notifier, clock):
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    await poller.run_cycle()
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), ev(10, "Beta"))
    clock.advance(timedelta(minutes=20))
    await poller.run_cycle()
    second = notifier.sent[1][1]
    assert "Beta" in second
    assert "Alpha" not in second


async def test_same_code_two_users_one_fetch_two_messages(poller, repo, fakes, notifier):
    await add(repo, SPX, "spx", user_id=ADMIN)
    await add(repo, SPX, "spx", user_id=USER)
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0))
    await poller.run_cycle()
    assert len(fakes["spx"].calls) == 1
    assert sorted(cid for cid, _, _ in notifier.sent) == [USER, ADMIN]


async def test_jt_groups_by_phone(poller, repo, fakes):
    await add(repo, JT, "jt", user_id=ADMIN, last4="1111")
    await add(repo, JT, "jt", user_id=USER, last4="2222")
    await poller.run_cycle()
    assert sorted(fakes["jt"].calls) == [(JT, "1111"), (JT, "2222")]


async def test_pacing_sleeps_between_same_carrier_only(poller, repo, sleeps):
    for index in range(1, 4):
        await add(repo, f"SPXVN00000000000{index}", "spx")
    await add(repo, JT, "jt", last4="1111")
    await poller.run_cycle()
    assert sleeps == [4.0, 4.0]


async def test_delivered_transition(poller, repo, fakes, notifier, clock):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0), ev(30), delivered=True)
    await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert refreshed.state == "delivered"
    assert refreshed.delivered_at == ev(30).time
    assert notifier.sent[0][1].endswith(texts.UPDATE_DELIVERED)
    clock.advance(timedelta(days=1))
    await poller.run_cycle()
    assert len(fakes["spx"].calls) == 1


async def test_delivered_footer_not_repeated(poller, repo, fakes, notifier, clock):
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    await poller.run_cycle()
    fakes["spx"].results[(SPX, None)] = found(
        "spx", SPX, ev(0, "Alpha"), ev(10, "Beta"), delivered=True
    )
    clock.advance(timedelta(minutes=20))
    await poller.run_cycle()
    clock.advance(timedelta(days=1))
    await poller.run_cycle()
    footers = [text for _, text, _ in notifier.sent if texts.UPDATE_DELIVERED in text]
    assert len(footers) == 1
    assert texts.UPDATE_DELIVERED not in notifier.sent[0][1]
    assert len(fakes["spx"].calls) == 2


async def test_not_found_young_stays_pending_no_message(poller, repo, notifier):
    parcel = await add(repo, SPX, "spx", created=T0 - timedelta(days=2))
    await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert refreshed.state == "pending"
    assert refreshed.next_check_at == T0 + timedelta(minutes=20)
    assert notifier.sent == []


async def test_not_found_after_seven_days_expires(poller, repo, notifier):
    parcel = await add(repo, SPX, "spx", created=T0 - timedelta(days=8))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).state == "expired"
    assert len(notifier.sent) == 1
    assert "Sau 7 ngày" in notifier.sent[0][1]


async def test_not_found_with_existing_events_counts_failure(poller, repo, notifier):
    parcel = await add(repo, SPX, "spx")
    await repo.insert_events(parcel.id, [ev(0)], T0)
    await repo.set_state(parcel.id, "in_transit", T0)
    report = await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert refreshed.consecutive_failures == 1
    assert refreshed.state == "in_transit"
    assert notifier.sent == []
    assert report.failures == {"spx": 1}


async def test_failure_backoff_schedule(poller, repo, fakes, clock):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    # 20 minutes doubling, until the two-hour ceiling takes over.
    expected_minutes = [40, 80, 120, 120, 120]
    for minutes in expected_minutes:
        now = clock()
        await poller.run_cycle()
        refreshed = await repo.get_parcel(parcel.id)
        assert refreshed.next_check_at == now + timedelta(minutes=minutes)
        clock.set(refreshed.next_check_at)


async def drive_failures(poller, repo, clock, parcel_id, cycles):
    for _ in range(cycles):
        await poller.run_cycle()
        clock.set((await repo.get_parcel(parcel_id)).next_check_at)


async def test_alert_on_fifth_failure_with_cooldown(poller, repo, fakes, notifier, clock):
    first = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "parse", "bad json")
    await drive_failures(poller, repo, clock, first.id, 5)
    alerts = messages_to(notifier, ADMIN)
    assert len(alerts) == 1
    assert "5 lỗi liên tiếp" in alerts[0]
    assert notifier.sent[0][2] is False
    await poller.run_cycle()
    assert len(messages_to(notifier, ADMIN)) == 1

    await repo.set_state(first.id, "stale", clock())
    second_code = "SPXVN000000000002"
    second = await repo.add_parcel(
        user_id=USER,
        carrier="spx",
        candidates=("spx",),
        tracking_number=second_code,
        phone_last4=None,
        now=clock(),
        next_check_at=clock(),
    )
    fakes["spx"].results[(second_code, None)] = CarrierError("spx", "parse", "bad json")
    await drive_failures(poller, repo, clock, second.id, 5)
    assert len(messages_to(notifier, ADMIN)) == 2


async def test_alert_when_all_fetches_fail_min_three(
    repo, fakes, notifier, settings, clock, sleeps
):
    poller = make_poller(repo, fakes, notifier, settings, clock, sleeps)
    for index in range(1, 4):
        code = f"SPXVN00000000000{index}"
        await add(repo, code, "spx")
        fakes["spx"].results[(code, None)] = CarrierError("spx", "network", "timeout")
    await poller.run_cycle()
    assert len(messages_to(notifier, ADMIN)) == 1


async def test_no_alert_when_only_two_fetches_fail(poller, repo, fakes, notifier):
    for index in range(1, 3):
        code = f"SPXVN00000000000{index}"
        await add(repo, code, "spx")
        fakes["spx"].results[(code, None)] = CarrierError("spx", "network", "timeout")
    await poller.run_cycle()
    assert messages_to(notifier, ADMIN) == []


async def test_stale_after_thirty_days(poller, repo, fakes, notifier):
    parcel = await add(repo, SPX, "spx", created=T0 - timedelta(days=40))
    old = TrackingEvent(time=T0 - timedelta(days=31), description="Đang vận chuyển")
    await repo.insert_events(parcel.id, [old], T0)
    await repo.record_check_success(
        parcel.id,
        state="in_transit",
        last_status_text=old.description,
        last_event_at=old.time,
        next_check_at=T0,
        now=T0,
    )
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, old)
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).state == "stale"
    assert len(notifier.sent) == 1
    assert "30 ngày" in notifier.sent[0][1]


async def test_stale_stays_stale_without_new_events(poller, repo, fakes, notifier):
    parcel = await add(repo, SPX, "spx", created=T0 - timedelta(days=40))
    old = TrackingEvent(time=T0 - timedelta(days=31), description="Đang vận chuyển")
    await repo.insert_events(parcel.id, [old], T0)
    await repo.record_check_success(
        parcel.id,
        state="stale",
        last_status_text=old.description,
        last_event_at=old.time,
        next_check_at=T0,
        now=T0,
    )
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, old)
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).state == "stale"
    assert len(notifier.sent) == 0


async def test_stale_revives_with_new_events(poller, repo, fakes, notifier):
    parcel = await add(repo, SPX, "spx", created=T0 - timedelta(days=40))
    old = TrackingEvent(time=T0 - timedelta(days=31), description="Đang vận chuyển")
    await repo.insert_events(parcel.id, [old], T0)
    await repo.record_check_success(
        parcel.id,
        state="stale",
        last_status_text=old.description,
        last_event_at=old.time,
        next_check_at=T0,
        now=T0,
    )
    new_event = TrackingEvent(time=T0, description="Đã đến kho phân loại")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, old, new_event)
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).state == "in_transit"
    assert len(notifier.sent) == 1


async def test_quiet_hours_silent_flag(repo, fakes, notifier, settings, clock, sleeps):
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0))
    clock.set(datetime(2026, 9, 1, 16, 0, tzinfo=UTC))
    await repo._conn.execute("UPDATE parcels SET next_check_at = ?", (clock().isoformat(),))
    await repo._conn.commit()
    await make_poller(repo, fakes, notifier, settings, clock, sleeps).run_cycle()
    assert notifier.sent[0][2] is True


@pytest.mark.parametrize(
    ("quiet", "hour_utc", "expected"),
    [
        ((22, 7), 16, True),
        ((22, 7), 23, True),
        ((22, 7), 0, False),
        ((22, 7), 5, False),
        ((1, 5), 18, True),
        ((1, 5), 22, False),
        (None, 16, False),
    ],
)
def test_is_quiet_wraparound_and_normal_ranges(
    repo, fakes, notifier, settings, clock, sleeps, quiet, hour_utc, expected
):
    poller = make_poller(repo, fakes, notifier, replace(settings, quiet_hours=quiet), clock, sleeps)
    assert poller.is_quiet(datetime(2026, 9, 1, hour_utc, 0, tzinfo=UTC)) is expected


async def test_revoked_user_not_polled(poller, repo, fakes):
    await add(repo, SPX, "spx")
    await repo.upsert_user(USER, now=T0, is_allowed=False)
    await poller.run_cycle()
    assert fakes["spx"].calls == []


async def test_only_user_id_ignores_schedule(poller, repo, fakes):
    await add(repo, SPX, "spx", user_id=USER, due=False)
    await add(repo, "SPXVN000000000002", "spx", user_id=ADMIN, due=True)
    report = await poller.run_cycle(only_user_id=USER)
    assert fakes["spx"].calls == [(SPX, None)]
    assert report.parcels_checked == 1
    assert await repo.get_meta("last_poll_at") is None


async def test_skipped_when_locked(poller, repo):
    await poller._lock.acquire()
    try:
        assert (await poller.run_cycle()).skipped is True
        waiting = asyncio.create_task(poller.run_cycle(wait=True))
        await asyncio.sleep(0)
        assert not waiting.done()
    finally:
        poller._lock.release()
    report = await waiting
    assert report.skipped is False


async def test_notifier_failure_does_not_stop_cycle(repo, fakes, settings, clock, sleeps):
    failing = FakeNotifier(fail_with=RuntimeError("telegram down"))
    poller = make_poller(repo, fakes, failing, settings, clock, sleeps)
    first = await add(repo, SPX, "spx")
    second = await add(repo, "SPXVN000000000002", "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0))
    fakes["spx"].results[("SPXVN000000000002", None)] = found("spx", "SPXVN000000000002", ev(5))
    report = await poller.run_cycle()
    assert await repo.count_events(first.id) == 1
    assert await repo.count_events(second.id) == 1
    assert report.messages_sent == 0
    assert len(failing.sent) == 1, "both parcels share one grouped message"


async def test_purges_old_terminal(poller, repo):
    parcel = await add(repo, SPX, "spx", due=False)
    await repo.set_state(parcel.id, "delivered", T0 - timedelta(days=31))
    await poller.run_cycle()
    assert await repo.get_parcel(parcel.id) is None


async def test_report_saved_to_meta(poller, repo):
    await add(repo, SPX, "spx")
    await poller.run_cycle()
    report = json.loads(await repo.get_meta("last_poll_report"))
    assert {"fetches", "new_events", "failures", "skipped"} <= set(report)
    assert report["fetches"] == 1
    assert await repo.get_meta("last_poll_at") is not None


async def test_unresolved_resolves_on_found_candidate(poller, repo, fakes, notifier):
    parcel = await add(repo, GEN, None, candidates=("ghn", "ninjavan"), last4="1111")
    fakes["ninjavan"].results[(GEN, None)] = found("ninjavan", GEN, ev(0, "Đã nhập kho"))
    await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert (refreshed.carrier, refreshed.candidates, refreshed.state) == (
        "ninjavan",
        ("ninjavan",),
        "in_transit",
    )
    assert fakes["ghn"].calls == [(GEN, "1111")]
    assert len(notifier.sent) == 1
    assert "Đã xác định hãng vận chuyển: <b>Ninja Van</b>" in notifier.sent[0][1]
    assert "Đã nhập kho" in notifier.sent[0][1]


async def test_unresolved_prefers_candidate_order(poller, repo, fakes):
    parcel = await add(repo, GEN, None, candidates=("ghn", "ninjavan"), last4="1111")
    fakes["ghn"].results[(GEN, "1111")] = found("ghn", GEN, ev(0))
    fakes["ninjavan"].results[(GEN, None)] = found("ninjavan", GEN, ev(5))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).carrier == "ghn"


async def test_unresolved_all_errors_one_failure(poller, repo, fakes, notifier):
    parcel = await add(repo, GEN, None, candidates=("ghn", "ninjavan"), last4="1111")
    fakes["ghn"].results[(GEN, "1111")] = CarrierError("ghn", "blocked", "403")
    fakes["ninjavan"].results[(GEN, None)] = CarrierError("ninjavan", "network", "timeout")
    report = await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).consecutive_failures == 1
    assert report.failures == {"ghn": 1, "ninjavan": 1}
    assert notifier.sent == []


async def test_unresolved_error_and_not_found_counts_failure(poller, repo, fakes, notifier):
    parcel = await add(repo, GEN, None, candidates=("ghn", "ninjavan"), last4="1111")
    fakes["ghn"].results[(GEN, "1111")] = CarrierError("ghn", "blocked", "403")
    await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert refreshed.consecutive_failures == 1
    assert refreshed.state == "pending"
    assert notifier.sent == []


async def test_unresolved_expires_after_seven_days(poller, repo, notifier):
    parcel = await add(
        repo,
        GEN,
        None,
        candidates=("ghn", "ninjavan"),
        last4="1111",
        created=T0 - timedelta(days=8),
    )
    await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert (refreshed.state, refreshed.carrier) == ("expired", None)
    assert "Sau 7 ngày" in notifier.sent[0][1]


async def test_unresolved_without_digits_skips_phone_candidate(poller, repo, fakes):
    await add(repo, GEN, None, candidates=("ghn", "ninjavan"))
    await poller.run_cycle()
    assert fakes["ghn"].calls == []
    assert fakes["ninjavan"].calls == [(GEN, None)]


async def test_resolved_next_cycle_uses_single_key(poller, repo, fakes, clock):
    await add(repo, GEN, None, candidates=("ghn", "ninjavan"), last4="1111")
    fakes["ninjavan"].results[(GEN, None)] = found("ninjavan", GEN, ev(0))
    await poller.run_cycle()
    clock.advance(timedelta(minutes=20))
    await poller.run_cycle()
    assert len(fakes["ghn"].calls) == 1
    assert len(fakes["ninjavan"].calls) == 2


class DeletingCarrier(FakeCarrier):
    def __init__(self, code, repo, parcel_ids):
        super().__init__(code)
        self._repo = repo
        self._parcel_ids = parcel_ids

    async def fetch(self, http, tracking_number, phone_last4=None):
        for parcel_id in self._parcel_ids:
            await self._repo.delete_parcel(parcel_id)
        return await super().fetch(http, tracking_number, phone_last4)


async def test_delivered_status_without_new_event_notifies(poller, repo, fakes, notifier, clock):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    await poller.run_cycle()
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), delivered=True)
    clock.advance(timedelta(minutes=20))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).state == "delivered"
    assert len(notifier.sent) == 2
    assert notifier.sent[1][1].endswith(texts.UPDATE_DELIVERED)


async def test_parcel_removed_during_fetch_is_skipped(poller, repo, fakes, notifier):
    removed = await add(repo, SPX, "spx")
    kept_code = "SPXVN000000000002"
    await add(repo, kept_code, "spx")
    deleting = DeletingCarrier("spx", repo, [removed.id])
    deleting.results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    deleting.results[(kept_code, None)] = found("spx", kept_code, ev(5, "Beta"))
    fakes["spx"] = deleting
    await poller.run_cycle()
    assert await repo.get_parcel(removed.id) is None
    texts_sent = [text for _, text, _ in notifier.sent]
    assert not any("Alpha" in text for text in texts_sent)
    assert any("Beta" in text for text in texts_sent)
    assert await repo.get_meta("last_poll_report") is not None


async def test_unresolved_parcel_removed_during_fetch_is_skipped(poller, repo, fakes, notifier):
    parcel = await add(repo, GEN, None, candidates=("ghn", "ninjavan"))
    deleting = DeletingCarrier("ninjavan", repo, [parcel.id])
    deleting.results[(GEN, None)] = found("ninjavan", GEN, ev(0))
    fakes["ninjavan"] = deleting
    await poller.run_cycle()
    assert await repo.get_parcel(parcel.id) is None
    assert notifier.sent == []


async def test_failing_pending_parcel_expires_after_seven_days(poller, repo, fakes, notifier):
    parcel = await add(repo, SPX, "spx", created=T0 - timedelta(days=8))
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    await poller.run_cycle()
    refreshed = await repo.get_parcel(parcel.id)
    assert refreshed.state == "expired"
    assert refreshed.consecutive_failures == 0
    assert len(notifier.sent) == 1
    assert "Sau 7 ngày" in notifier.sent[0][1]


async def test_parcel_without_loaded_module_is_skipped_with_warning(poller, repo, caplog):
    caplog.set_level("WARNING")
    await add(repo, "XX0000000001", "oldcarrier")
    report = await poller.run_cycle()
    assert report.fetches == 0
    assert "carrier module missing carrier=oldcarrier parcels=1" in caplog.text


async def test_found_result_stores_progress_and_update_shows_bar(poller, repo, fakes, notifier):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).progress == 95
    text = notifier.sent[0][1]
    assert " · 95%" in text.split("\n")[2], "the parcel line carries its progress"
    assert "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟥" in text


async def test_update_message_has_card_buttons_and_is_silent(poller, repo, fakes, notifier):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"))
    await poller.run_cycle()
    assert notifier.sent[0][2] is True
    assert notifier.markups[0].inline_keyboard[0][0].callback_data == f"p:{parcel.id}:card:1", (
        "one grouped message carries numbered buttons, not one parcel's card"
    )


async def test_out_for_delivery_and_delivered_ring(poller, repo, fakes, notifier, clock):
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    await poller.run_cycle()
    assert notifier.sent[-1][2] is False
    clock.advance(timedelta(hours=1))
    fakes["spx"].results[(SPX, None)] = found(
        "spx", SPX, ev(0, "Đang giao hàng"), ev(5, "Giao hàng thành công"), delivered=True
    )
    await poller.run_cycle()
    assert len(notifier.sent) == 2
    assert notifier.sent[-1][2] is False


async def test_sticker_sent_before_update_and_skipped_after_failure(
    poller, repo, fakes, notifier, clock, caplog
):
    await repo.set_meta("sticker:spx", "file-spx")
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"))
    await poller.run_cycle()
    assert notifier.stickers == [(USER, "file-spx")]
    notifier.sticker_ok = False
    clock.advance(timedelta(hours=1))
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đã đến kho"), ev(5, "Rời kho"))
    await poller.run_cycle()
    clock.advance(timedelta(hours=1))
    fakes["spx"].results[(SPX, None)] = found(
        "spx", SPX, ev(0, "Đã đến kho"), ev(5, "Rời kho"), ev(9, "Đến kho 2")
    )
    await poller.run_cycle()
    assert len(notifier.stickers) == 2
    assert caplog.text.count("carrier sticker failed carrier=spx") == 1
    assert len(notifier.sent) == 3


async def test_check_parcel_only_checks_that_parcel(poller, repo, fakes):
    first = await add(repo, SPX, "spx")
    await add(repo, "SPXVN000000000002", "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    checked = await poller.check_parcel(USER, first.id)
    assert checked.progress == 95
    assert fakes["spx"].calls == [(SPX, None)]
    assert await poller.check_parcel(999, first.id) is None


async def test_next_check_follows_the_delivery_stage(poller, repo, fakes):
    other = "SPXVN000000000002"
    transit = await add(repo, SPX, "spx")
    near = await add(repo, other, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    fakes["spx"].results[(other, None)] = found("spx", other, ev(0, "Đang giao hàng"))
    await poller.run_cycle()
    assert (await repo.get_parcel(transit.id)).next_check_at == T0 + timedelta(minutes=10)
    assert (await repo.get_parcel(near.id)).next_check_at == T0 + timedelta(minutes=3)


async def test_in_transit_failures_back_off_from_the_stage_interval(poller, repo, fakes):
    parcel = await add(repo, SPX, "spx")
    await repo.set_state(parcel.id, "in_transit", T0)
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).next_check_at == T0 + timedelta(minutes=20)


async def test_idle_tick_records_the_poll_without_logging(poller, repo, caplog):
    caplog.set_level("INFO")
    report = await poller.run_cycle()
    assert report.parcels_checked == 0
    assert await repo.get_meta("last_poll_at") == T0.isoformat()
    assert "poll cycle" not in caplog.text


async def descriptions(repo, parcel_id):
    return [event.description for event in await repo.list_events(parcel_id, 10)]


async def test_rebuild_replaces_history_and_progress_without_repeating_updates(
    poller, repo, fakes, notifier
):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), ev(5, "Đang giao hàng"))
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).progress == 95
    sent = len(notifier.sent)
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), ev(5, "Beta"))
    report = await poller.run_cycle(only_user_id=USER, wait=True, rebuild=True)
    assert report.rebuilt == 1
    assert report.new_events == 0
    assert await descriptions(repo, parcel.id) == ["Alpha", "Beta"]
    fresh = await repo.get_parcel(parcel.id)
    assert fresh.progress != 95
    assert fresh.last_status_text == "Beta"
    assert len(notifier.sent) == sent


async def test_rebuild_still_reports_events_newer_than_the_stored_history(
    poller, repo, fakes, notifier
):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    await poller.run_cycle()
    sent = len(notifier.sent)
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha fixed"), ev(30, "Beta"))
    report = await poller.run_cycle(only_user_id=USER, wait=True, rebuild=True)
    assert report.new_events == 1
    assert len(notifier.sent) == sent + 1
    assert "Beta" in notifier.sent[-1][1]
    assert "Alpha fixed" not in notifier.sent[-1][1]
    assert await descriptions(repo, parcel.id) == ["Alpha fixed", "Beta"]


async def test_rebuild_failure_keeps_the_stored_history(poller, repo, fakes):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    await poller.run_cycle()
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    report = await poller.run_cycle(only_user_id=USER, wait=True, rebuild=True)
    assert report.rebuilt == 0
    assert await descriptions(repo, parcel.id) == ["Alpha"]


async def test_rebuild_includes_recently_finished_parcels(poller, repo, fakes):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), delivered=True)
    await poller.run_cycle()
    assert (await repo.get_parcel(parcel.id)).state == "delivered"
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    await poller.run_cycle(only_user_id=USER, wait=True, rebuild=True)
    finished = await repo.get_parcel(parcel.id)
    assert (finished.state, finished.consecutive_failures) == ("delivered", 0)
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"), ev(10, "Beta"))
    report = await poller.run_cycle(only_user_id=USER, wait=True, rebuild=True)
    assert report.rebuilt == 1
    assert await descriptions(repo, parcel.id) == ["Alpha", "Beta"]


async def test_rebuild_resets_failure_counts(poller, repo, fakes):
    parcel = await add(repo, SPX, "spx")
    for _ in range(3):
        await repo.record_check_failure(parcel.id, next_check_at=T0, now=T0)
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    await poller.run_cycle(only_user_id=USER, wait=True, rebuild=True)
    assert (await repo.get_parcel(parcel.id)).consecutive_failures == 1


async def test_check_parcel_rebuild_replaces_that_parcel(poller, repo, fakes):
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    await poller.run_cycle()
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Alpha"))
    checked = await poller.check_parcel(USER, parcel.id, rebuild=True)
    assert checked.progress != 95
    assert await descriptions(repo, parcel.id) == ["Alpha"]


async def test_a_failing_order_is_tried_again_within_the_ceiling(poller, repo, fakes, clock):
    """Backoff doubles, but never past the ceiling: this is what froze a real parcel."""
    parcel = await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "parse", "no result")
    await drive_failures(poller, repo, clock, parcel.id, 7)
    now = clock()
    await poller.run_cycle()
    stored = await repo.get_parcel(parcel.id)
    assert stored.consecutive_failures == 8, "every cycle failed"
    assert stored.next_check_at - now <= MAX_CHECK_GAP


async def test_two_parcels_moving_together_arrive_as_one_message(poller, repo, fakes, notifier):
    """A carrier writing several scans at once should not mean several notifications."""
    await add(repo, SPX, "spx")
    await add(repo, "SPXVN000000000002", "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    fakes["spx"].results[("SPXVN000000000002", None)] = found(
        "spx", "SPXVN000000000002", ev(5, "Đã đến kho")
    )
    report = await poller.run_cycle()
    sent = messages_to(notifier, USER)
    assert len(sent) == 1, "one message for the whole check"
    assert report.messages_sent == 1
    assert texts.UPDATES_HEADER in sent[0]
    assert "Đang giao hàng" in sent[0]
    assert "Đã đến kho" in sent[0]


async def test_each_owner_gets_their_own_message(poller, repo, fakes, notifier):
    """Grouping is per person: one family member never sees another's parcels."""
    await add(repo, SPX, "spx", user_id=USER)
    await add(repo, "SPXVN000000000002", "spx", user_id=ADMIN)
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Của bạn"))
    fakes["spx"].results[("SPXVN000000000002", None)] = found(
        "spx", "SPXVN000000000002", ev(5, "Của người khác")
    )
    await poller.run_cycle()
    mine = messages_to(notifier, USER)
    theirs = messages_to(notifier, ADMIN)
    assert len(mine) == 1 and len(theirs) == 1
    assert "Của bạn" in mine[0] and "Của người khác" not in mine[0]
    assert "Của người khác" in theirs[0] and "Của bạn" not in theirs[0]


async def test_a_delivery_in_the_group_still_arrives_with_sound(poller, repo, fakes, notifier):
    """Ordinary movement stays quiet; a delivery in the same message still pings."""
    await add(repo, SPX, "spx")
    await add(repo, "SPXVN000000000002", "spx")
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "Đang giao hàng"))
    fakes["spx"].results[("SPXVN000000000002", None)] = found(
        "spx", "SPXVN000000000002", ev(5, "Giao hàng thành công"), delivered=True
    )
    await poller.run_cycle()
    silent_flags = [silent for chat, _, silent in notifier.sent if chat == USER]
    assert silent_flags == [False], "the message carries sound because one parcel was delivered"


async def test_only_the_newest_scan_of_each_parcel_is_shown(poller, repo, fakes, notifier):
    """The wall of history is what made these unreadable."""
    await add(repo, SPX, "spx")
    fakes["spx"].results[(SPX, None)] = found(
        "spx", SPX, ev(0, "Cũ nhất"), ev(10, "Ở giữa"), ev(20, "Mới nhất")
    )
    await poller.run_cycle()
    sent = messages_to(notifier, USER)[0]
    assert "Mới nhất" in sent
    assert "Cũ nhất" not in sent
    assert "Ở giữa" not in sent
