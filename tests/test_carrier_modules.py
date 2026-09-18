from datetime import UTC, datetime, timedelta

import pytest

from vn_parcel_bot.carriers.models import TrackingEvent
from vn_parcel_bot.carriers.modules.spx import spx_place
from vn_parcel_bot.carriers.registry import CarrierRegistry

ORDER = [
    "spx",
    "jt",
    "cainiao",
    "fourpx",
    "ninjavan",
    "ghn",
    "best",
    "yunexpress",
    "ghtk",
    "viettelpost",
    "vnpost",
    "lex",
    "sf",
]


@pytest.fixture(scope="module")
def snapshot():
    registry = CarrierRegistry.load()
    assert registry.startup_rejections == []
    return registry.current


def test_builtin_modules_in_display_order(snapshot):
    assert [module.code for module in snapshot.ordered()] == ORDER


def test_tracked_and_phone_carriers(snapshot):
    tracked = [module.code for module in snapshot.ordered() if snapshot.is_tracked(module.code)]
    assert tracked == ["spx", "jt", "cainiao", "fourpx", "ninjavan", "ghn"]
    assert {module.code for module in snapshot.ordered() if module.needs_phone} == {
        "jt",
        "ghn",
        "best",
    }


def test_display_names(snapshot):
    assert snapshot.display_name("jt") == "🔴 J&T"
    assert snapshot.display_name("lex") == "💙 LEX VN"
    assert snapshot.display_name("fourpx") == "📦 4PX"
    assert snapshot.display_name("sf") == "✈️ SF Express"


def test_links(snapshot):
    assert snapshot.link("ghtk", "S123.AB") == "https://i.ghtk.vn/S123.AB"
    assert "YT1%232" in snapshot.link("yunexpress", "YT1#2")
    assert (
        snapshot.link("viettelpost", "123") == "https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/"
    )
    assert (
        snapshot.link("spx", "SPXVN05338454932C") == "https://spx.vn/track?spx_tn=SPXVN05338454932C"
    )
    assert snapshot.link("jt", "JNTXB1013176787") == (
        "https://vntracuu.com/search-tracking?search=JNTXB1013176787&operator=jandt"
    )
    # A carrier the bot tracks but has no page of its own still falls back to 17TRACK.
    assert snapshot.link("ninjavan", "SPEVN000000000001") is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("SPXVN05338454932C", ["spx"]),
        ("SPEVN000000000001", ["ninjavan"]),
        ("LP00123456789012", ["cainiao"]),
        ("LX123456789CN", ["cainiao"]),
        ("4PX3000123456789CN", ["fourpx"]),
        ("YT1234567890123456", ["yunexpress"]),
        ("YT0000000000001", ["cainiao"]),
        ("SF0000000000001", ["sf"]),
        ("SF123456789012", ["sf"]),
        ("SF123456789012345", ["sf"]),
        ("LP0012345678901234", ["cainiao"]),
        ("EB123456789VN", ["vnpost"]),
        ("EMS1234567890", ["vnpost"]),
        ("LEXVN00123456", ["lex"]),
        ("S1234567.MB12.D5.123456789", ["ghtk"]),
        ("GHTK0012345678", ["ghtk"]),
        ("JNTXB0000000001", ["jt"]),
        ("JNTX0000000001", ["jt"]),
        ("JTE1000000001", ["jt"]),
        ("JNTVN000000001", ["jt"]),
        ("BESTMP0000000001VNA", ["best"]),
        ("BEST0000000001VN", ["best"]),
        ("BEST0000000001", ["best"]),
        ("841000072647", ["jt", "best", "viettelpost"]),
        ("8410000726470", ["best"]),
        ("773440000000001", ["cainiao"]),
        ("500000000000001", ["cainiao"]),
        ("VTP0000000001", ["viettelpost"]),
        ("NLVN000000000001", ["ninjavan"]),
        ("YT123456789012345678", ["yunexpress"]),
        ("GAN6DKKU12", ["ghn", "ninjavan"]),
    ],
)
def test_detect_each_rule(snapshot, code, expected):
    assert list(snapshot.detect(code).candidates) == expected


@pytest.mark.parametrize(
    "code",
    [
        "",
        "AB12",
        "ABCDEFGH",
        "12345678",
        "71426082060",
        "GAN6DKKU12345678",
        "84000000000001",
        "94000000000001",
        "7734400000000011",
    ],
)
def test_detect_no_match(snapshot, code):
    assert snapshot.detect(code).candidates == ()


def test_generic_rule_is_standalone_only(snapshot):
    assert snapshot.detect("GAN6DKKU12").standalone_only
    assert not snapshot.detect("841000072647").standalone_only


def test_pending_hints(snapshot):
    assert "J&amp;T" in snapshot.pending_hint(("jt",), "JNTXB0000000001")
    assert snapshot.pending_hint(("jt",), "841000072647") is None
    assert "app Lazada" in snapshot.pending_hint(("cainiao",), "YT0000000000001")
    assert snapshot.pending_hint(("cainiao",), "LP00000000000001") is None


def test_clients_match_their_modules(snapshot):
    for code, client in snapshot.clients.items():
        module = snapshot.get(code)
        assert (client.code, client.display_name, client.needs_phone) == (
            code,
            module.display_name,
            module.needs_phone,
        )


def test_best_and_sf_clients_with_and_without_key(monkeypatch):
    from vn_parcel_bot.carriers.modules.best import build_best_client
    from vn_parcel_bot.carriers.modules.sf import build_sf_client
    from vn_parcel_bot.carriers.seventeen_track import SeventeenTrackCarrier

    monkeypatch.delenv("SEVENTEEN_TRACK_KEY", raising=False)
    assert build_best_client() is None
    assert build_sf_client() is None

    monkeypatch.setenv("SEVENTEEN_TRACK_KEY", "test-token")
    best_client = build_best_client()
    assert isinstance(best_client, SeventeenTrackCarrier)
    assert best_client.code == "best"
    assert best_client.seventeen_carrier_id == 101194
    # 17TRACK asks BEST registrations for the recipient's last 4 digits.
    assert best_client.needs_phone is True

    sf_client = build_sf_client()
    assert isinstance(sf_client, SeventeenTrackCarrier)
    assert sf_client.code == "sf"
    assert sf_client.seventeen_carrier_id == 100012
    assert sf_client.needs_phone is False


AT = datetime(2026, 9, 15, 1, 0, tzinfo=UTC)


def event(minutes, description, location=None):
    return TrackingEvent(
        time=AT + timedelta(minutes=minutes), description=description, location=location
    )


def test_spx_place_reads_the_hub_from_the_status_text():
    arrived = event(0, "Đơn hàng đã đến kho 21-HNI Thanh Tri 2 Hub")
    assert spx_place(arrived) == "21-HNI Thanh Tri 2 Hub"
    assert spx_place(event(0, "Đơn hàng đã rời kho BN B Mega SOC")) == "BN B Mega SOC"
    assert spx_place(event(0, "Đang giao hàng")) is None
    assert spx_place(event(0, "Đơn hàng đã đến kho", location="Kho HCM")) == "Kho HCM"


def test_latest_place_takes_the_newest_event_with_a_place(snapshot):
    events = [
        event(0, "Đơn hàng đã đến kho 11-TQG Son Duong Hub"),
        event(30, "Đơn hàng đã đến kho 21-HNI Thanh Tri 2 Hub"),
        event(60, "Đang giao hàng"),
    ]
    assert snapshot.latest_place("spx", events) == "21-HNI Thanh Tri 2 Hub"
    post_office = event(0, "Đã đến", location=" Bưu cục  Quận 7 ")
    assert snapshot.latest_place("jt", [post_office]) == "Bưu cục Quận 7"
    assert snapshot.latest_place(None, [post_office]) is None
    # 17TRACK can identify a carrier we carry no module for: the event's own place is used.
    assert snapshot.latest_place("gone", [post_office]) == "Bưu cục Quận 7"
    assert snapshot.latest_place("gone", [event(0, "Đang giao hàng", location=None)]) is None
