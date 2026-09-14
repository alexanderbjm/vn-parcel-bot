from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeCarrier, FakeClock, ev, found
from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService

T0 = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
SPX = "SPXVN000000000001"
SPX2 = "SPXVN000000000002"
JT = "840000000001"
GEN = "GA0000000001"
VNP = "EB123456789VN"
FPX = "4PX0000000000000001"


@pytest.fixture
async def repo(tmp_path):
    r = await Repository.open(tmp_path / "t.sqlite3")
    yield r
    await r.close()


@pytest.fixture
def clock():
    return FakeClock(T0)


@pytest.fixture
def fakes():
    return {code: FakeCarrier(code) for code in ("spx", "jt", "cainiao", "ninjavan", "ghn")}


@pytest.fixture
def service(repo, fakes, settings, clock):
    return ParcelService(repo, fakes, None, settings, clock)


@pytest.fixture
async def user(repo):
    return await repo.upsert_user(1, now=T0, name="A", is_allowed=True)


async def user_with_phone(repo, last4="1111"):
    await repo.upsert_user(1, now=T0, name="A", is_allowed=True)
    await repo.set_default_phone(1, last4)
    return await repo.get_user(1)


def total_calls(fakes):
    return sum(len(fake.calls) for fake in fakes.values())


async def test_add_invalid_code(service, user, fakes):
    outcome = await service.add(user, "hello")
    assert outcome.kind == "invalid_code"
    assert total_calls(fakes) == 0


async def test_add_link_only_vnpost(service, user, fakes, repo):
    outcome = await service.add(user, VNP)
    assert outcome.kind == "link_only"
    assert outcome.code == VNP
    assert outcome.link_carriers == ("vnpost",)
    assert await repo.find_parcel(1, VNP) is None
    assert total_calls(fakes) == 0


async def test_add_tracked_but_unmapped_is_invalid(service, user):
    assert (await service.add(user, FPX)).kind == "invalid_code"


async def test_add_spx_found_in_transit(service, user, fakes, repo):
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0, "A"), ev(10, "B"))
    outcome = await service.add(user, SPX)
    assert outcome.kind == "added"
    assert outcome.result.found
    parcel = outcome.parcel
    assert (parcel.carrier, parcel.candidates, parcel.state) == ("spx", ("spx",), "in_transit")
    assert parcel.last_status_text == "B"
    assert parcel.last_event_at == ev(10).time
    assert parcel.next_check_at == T0 + timedelta(minutes=20)
    assert await repo.count_events(parcel.id) == 2
    assert fakes["spx"].calls == [(SPX, None)]


async def test_add_normalizes_code(service, user, repo):
    outcome = await service.add(user, " spxvn 0000-0000-0001 ")
    assert outcome.code == SPX
    assert await repo.find_parcel(1, SPX) is not None


async def test_add_spx_delivered_sets_delivered_at(service, user, fakes):
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0), ev(30), delivered=True)
    parcel = (await service.add(user, SPX)).parcel
    assert parcel.state == "delivered"
    assert parcel.delivered_at == ev(30).time


async def test_add_spx_not_found_pending_resolved(service, user):
    outcome = await service.add(user, SPX)
    assert outcome.kind == "added"
    assert outcome.result.found is False
    assert (outcome.parcel.carrier, outcome.parcel.state) == ("spx", "pending")
    assert outcome.parcel.consecutive_failures == 0
    assert outcome.error is None


async def test_add_single_candidate_error_records_backoff(service, user, fakes):
    fakes["spx"].results[(SPX, None)] = CarrierError("spx", "network", "timeout")
    outcome = await service.add(user, SPX)
    assert outcome.kind == "added"
    assert outcome.error.reason == "network"
    assert outcome.parcel.consecutive_failures == 1
    assert outcome.parcel.next_check_at == T0 + timedelta(minutes=40)


async def test_add_jt_without_phone_needs_phone(service, user, fakes, repo):
    outcome = await service.add(user, JT)
    assert outcome.kind == "needs_phone"
    assert outcome.candidates == ("jt",)
    assert await repo.find_parcel(1, JT) is None
    assert total_calls(fakes) == 0


async def test_add_jt_uses_default_phone(service, repo, fakes):
    phoned = await user_with_phone(repo)
    outcome = await service.add(phoned, JT)
    assert fakes["jt"].calls == [(JT, "1111")]
    assert outcome.parcel.phone_last4 == "1111"


async def test_add_jt_override_wins(service, repo, fakes):
    phoned = await user_with_phone(repo)
    await service.add(phoned, JT, "2222")
    assert fakes["jt"].calls == [(JT, "2222")]


async def test_add_jt_invalid_override(service, user):
    assert (await service.add(user, JT, "12a4")).kind == "invalid_phone"


async def test_add_jt_not_found_mentions_link_only(service, repo):
    phoned = await user_with_phone(repo)
    outcome = await service.add(phoned, JT)
    assert outcome.link_carriers == ("best", "viettelpost")
    assert outcome.parcel.carrier == "jt"


async def test_add_generic_resolves_second_candidate(service, repo, fakes):
    phoned = await user_with_phone(repo)
    fakes["ninjavan"].results[(GEN, None)] = found("ninjavan", GEN, ev(0, "Đã nhập kho"))
    outcome = await service.add(phoned, GEN)
    assert outcome.kind == "added"
    parcel = outcome.parcel
    assert (parcel.carrier, parcel.candidates, parcel.phone_last4) == (
        "ninjavan",
        ("ninjavan",),
        None,
    )
    assert fakes["ghn"].calls == [(GEN, "1111")]
    assert fakes["ninjavan"].calls == [(GEN, None)]


async def test_add_generic_stops_at_first_found(service, repo, fakes):
    phoned = await user_with_phone(repo)
    fakes["ghn"].results[(GEN, "1111")] = found("ghn", GEN, ev(0, "Đã lấy hàng"))
    outcome = await service.add(phoned, GEN)
    assert outcome.parcel.carrier == "ghn"
    assert outcome.parcel.phone_last4 == "1111"
    assert fakes["ninjavan"].calls == []


async def test_add_generic_without_phone_tries_ninjavan_then_asks(service, user, fakes, repo):
    outcome = await service.add(user, GEN)
    assert outcome.kind == "needs_phone"
    assert outcome.candidates == ("ghn",)
    assert fakes["ninjavan"].calls == [(GEN, None)]
    assert fakes["ghn"].calls == []
    assert await repo.find_parcel(1, GEN) is None


async def test_add_generic_without_phone_ninjavan_found(service, user, fakes):
    fakes["ninjavan"].results[(GEN, None)] = found("ninjavan", GEN, ev(0))
    outcome = await service.add(user, GEN)
    assert outcome.kind == "added"
    assert outcome.parcel.carrier == "ninjavan"
    assert fakes["ghn"].calls == []


async def test_add_generic_none_found_stores_unresolved(service, repo):
    phoned = await user_with_phone(repo)
    outcome = await service.add(phoned, GEN)
    parcel = outcome.parcel
    assert outcome.kind == "added"
    assert parcel.carrier is None
    assert parcel.candidates == ("ghn", "ninjavan")
    assert parcel.phone_last4 == "1111"
    assert parcel.state == "pending"
    assert outcome.result.found is False
    assert outcome.link_carriers == ()


async def test_add_generic_all_errors_records_failure(service, repo, fakes):
    phoned = await user_with_phone(repo)
    fakes["ghn"].results[(GEN, "1111")] = CarrierError("ghn", "blocked", "403")
    fakes["ninjavan"].results[(GEN, None)] = CarrierError("ninjavan", "network", "timeout")
    outcome = await service.add(phoned, GEN)
    assert outcome.parcel.consecutive_failures == 1
    assert outcome.error.carrier == "ninjavan"
    assert outcome.parcel.carrier is None


async def test_add_generic_error_then_not_found_is_pending_success(service, repo, fakes):
    phoned = await user_with_phone(repo)
    fakes["ghn"].results[(GEN, "1111")] = CarrierError("ghn", "blocked", "403")
    outcome = await service.add(phoned, GEN)
    assert outcome.parcel.consecutive_failures == 0
    assert outcome.error is None
    assert outcome.result.found is False


async def test_add_order_number_is_not_stored(service, user, fakes, repo):
    outcome = await service.add(user, "500000000000001")
    assert outcome.kind == "order_number"
    assert outcome.code == "500000000000001"
    assert await repo.find_parcel(1, "500000000000001") is None
    assert total_calls(fakes) == 0


async def test_add_unknown_code_like(service, user, fakes, repo):
    outcome = await service.add(user, "abc1234567890def")
    assert outcome.kind == "unknown_carrier"
    assert outcome.code == "ABC1234567890DEF"
    assert await repo.find_parcel(1, "ABC1234567890DEF") is None
    assert total_calls(fakes) == 0


async def test_add_best_code_is_link_only(service, user, fakes):
    outcome = await service.add(user, "BESTMP0000000001VNA")
    assert outcome.kind == "link_only"
    assert outcome.link_carriers == ("best",)
    assert total_calls(fakes) == 0


async def test_add_seller_fleet_is_not_stored(service, user, fakes, repo):
    outcome = await service.add(user, "84000000000001", "1234")
    assert outcome.kind == "seller_fleet"
    assert outcome.code == "84000000000001"
    assert await repo.find_parcel(1, "84000000000001") is None
    assert total_calls(fakes) == 0


async def test_add_duplicate_any_carrier(service, user, fakes):
    assert (await service.add(user, SPX)).kind == "added"
    assert (await service.add(user, SPX)).kind == "duplicate"
    assert total_calls(fakes) == 1


async def test_add_limit(repo, fakes, settings, clock, user):
    limited = ParcelService(repo, fakes, None, replace(settings, max_parcels_per_user=2), clock)
    assert (await limited.add(user, SPX)).kind == "added"
    assert (await limited.add(user, SPX2)).kind == "added"
    assert (await limited.add(user, "SPXVN000000000003")).kind == "limit"


async def test_list_for_hides_old_terminal(service, user, repo):
    old = (await service.add(user, SPX)).parcel
    recent = (await service.add(user, SPX2)).parcel
    await repo.set_state(old.id, "delivered", T0 - timedelta(days=4))
    await repo.set_state(recent.id, "delivered", T0 - timedelta(days=1))
    assert [p.id for p in await service.list_for(1)] == [recent.id]


async def test_resolve_by_index_and_code(service, user):
    first = (await service.add(user, SPX)).parcel
    second = (await service.add(user, SPX2)).parcel
    assert (await service.resolve(1, "1")).id == first.id
    assert (await service.resolve(1, " 2 ")).id == second.id
    assert (await service.resolve(1, SPX)).id == first.id
    assert (await service.resolve(1, SPX.lower())).id == first.id
    assert await service.resolve(1, "0") is None
    assert await service.resolve(1, "9") is None


async def test_remove_returns_parcel_and_deletes(service, user, repo):
    parcel = (await service.add(user, SPX)).parcel
    removed = await service.remove(1, "1")
    assert removed.id == parcel.id
    assert await repo.get_parcel(parcel.id) is None


async def test_remove_unknown_returns_none(service, user):
    assert await service.remove(1, SPX) is None


async def test_rename_sets_truncates_and_clears(service, user):
    await service.add(user, SPX)
    renamed = await service.rename(1, "1", "  " + "x" * 60 + "  ")
    assert renamed.label == "x" * 40
    assert (await service.rename(1, "1", None)).label is None
    await service.rename(1, "1", "Áo")
    assert (await service.rename(1, "1", "   ")).label is None
    assert await service.rename(1, "5", "x") is None


async def test_history_returns_recent_events_ascending(service, user, fakes):
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(20, "C"), ev(0, "A"), ev(10, "B"))
    await service.add(user, SPX)
    parcel, events = await service.history(1, "1")
    assert parcel.tracking_number == SPX
    assert [e.description for e in events] == ["A", "B", "C"]
    assert await service.history(1, "2") is None


async def test_set_default_phone_valid_invalid_clear(service, user, repo):
    await service.set_default_phone(1, "4321")
    assert (await repo.get_user(1)).default_phone_last4 == "4321"
    with pytest.raises(ValueError):
        await service.set_default_phone(1, "12")
    await service.set_default_phone(1, None)
    assert (await repo.get_user(1)).default_phone_last4 is None


async def test_other_users_parcels_invisible(service, user, repo):
    await service.add(user, SPX)
    await repo.upsert_user(2, now=T0, name="B", is_allowed=True)
    assert await service.resolve(2, "1") is None
    assert await service.remove(2, SPX) is None
    assert await service.list_for(2) == []


async def test_add_found_with_label(service, user, fakes):
    fakes["spx"].results[(SPX, None)] = found("spx", SPX, ev(0))
    outcome = await service.add(user, SPX, label="  Tai nghe Bluetooth  ")
    assert outcome.kind == "added"
    assert outcome.parcel.label == "Tai nghe Bluetooth"


async def test_add_pending_with_label_cut_to_max(service, user):
    outcome = await service.add(user, SPX, label="x" * 60)
    assert outcome.kind == "added"
    assert outcome.parcel.state == "pending"
    assert outcome.parcel.label == "x" * 40


async def test_add_blank_label_is_ignored(service, user):
    outcome = await service.add(user, SPX, label="   ")
    assert outcome.parcel.label is None


async def test_add_duplicate_sets_missing_label_only(service, user):
    await service.add(user, SPX)
    first = await service.add(user, SPX, label="Tai nghe")
    assert first.kind == "duplicate"
    assert first.parcel.label == "Tai nghe"
    second = await service.add(user, SPX, label="Ốp lưng")
    assert second.kind == "duplicate"
    assert second.parcel.label == "Tai nghe"


async def test_add_needs_phone_does_not_store_label(service, user, repo):
    outcome = await service.add(user, JT, label="Tai nghe")
    assert outcome.kind == "needs_phone"
    assert await repo.find_parcel(1, JT) is None


async def test_add_jt_cross_border_code_is_tracked_as_jt(service, repo, fakes):
    user = await user_with_phone(repo)
    outcome = await service.add(user, "JNTXB0000000001")
    assert outcome.kind == "added"
    assert outcome.parcel.carrier == "jt"
    assert outcome.parcel.state == "pending"
    assert outcome.parcel.phone_last4 == "1111"
    assert fakes["jt"].calls == [("JNTXB0000000001", "1111")]


async def test_add_lazada_cainiao_code_tracks_the_waybill(service, user, fakes, repo):
    outcome = await service.add(user, "500000000000001_YT0000000000001")
    assert outcome.kind == "added"
    assert outcome.parcel.carrier == "cainiao"
    assert outcome.parcel.tracking_number == "YT0000000000001"
    assert fakes["cainiao"].calls == [("YT0000000000001", None)]
    assert await repo.find_parcel(1, "500000000000001") is None
