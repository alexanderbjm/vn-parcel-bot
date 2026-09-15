import pytest

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
    assert {module.code for module in snapshot.ordered() if module.needs_phone} == {"jt", "ghn"}


def test_display_names(snapshot):
    assert snapshot.display_name("jt") == "J&T"
    assert snapshot.display_name("lex") == "LEX VN"
    assert snapshot.display_name("fourpx") == "4PX"
    assert snapshot.display_name("sf") == "SF Express"


def test_links(snapshot):
    assert snapshot.link("ghtk", "S123.AB") == "https://i.ghtk.vn/S123.AB"
    assert "YT1%232" in snapshot.link("yunexpress", "YT1#2")
    assert (
        snapshot.link("viettelpost", "123") == "https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/"
    )
    assert snapshot.link("spx", "SPXVN05338454932C") is None


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

    sf_client = build_sf_client()
    assert isinstance(sf_client, SeventeenTrackCarrier)
    assert sf_client.code == "sf"
    assert sf_client.seventeen_carrier_id == 100012
