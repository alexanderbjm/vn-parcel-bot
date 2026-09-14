import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeCarrier, FakeClock, FakeNotifier, ev, fake_registry, found
from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent
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
    assert "Alpha" in sent[0]
    assert "Beta" in sent[0]
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
    expected_minutes = [40, 80, 160, 320, 360]
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
    assert len(failing.sent) == 2


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
    assert text.split("\n")[0].endswith(" · 95%")
    assert "▓▓▓▓▓▓▓▓▓░" in text
