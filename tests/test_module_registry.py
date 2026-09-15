import textwrap

from vn_parcel_bot.carriers.registry import CarrierRegistry, Detection

ALPHA = r"""
from vn_parcel_bot.carriers.api import CarrierModule, Rule

MODULE = CarrierModule(
    code="alpha",
    display_name="Alpha & Co",
    order=1,
    rules=(Rule(r"AL\d{8}", 100), Rule(r"\d{12}", 40, rank=0)),
    link_template="https://alpha.example/track?c={code}",
    examples=(("AL00000001", True),),
)
"""

BETA = r"""
from vn_parcel_bot.carriers.api import CarrierModule, Rule
from vn_parcel_bot.carriers.models import TrackingResult


class BetaCarrier:
    code = "beta"
    display_name = "Beta"
    needs_phone = False

    async def fetch(self, http, tracking_number, phone_last4=None):
        return TrackingResult(carrier="beta", tracking_number=tracking_number, found=False)


def beta_hint(tracking_number):
    return "\nbeta hint" if tracking_number.startswith("BE") else None


MODULE = CarrierModule(
    code="beta",
    display_name="Beta",
    order=2,
    rules=(Rule(r"\d{12}", 40, rank=1), Rule(r"BE[0-9A-Z]{8}", 10, standalone_only=True)),
    examples=(("000000000001", True),),
    build_client=BetaCarrier,
    pending_hint=beta_hint,
)
"""

ZETA = r"""
from vn_parcel_bot.carriers.api import CarrierModule, Rule

MODULE = CarrierModule(
    code="zeta",
    display_name="Zeta",
    order=3,
    rules=(Rule(r"AL\d{8}", 200),),
    link_template="https://zeta.example/",
)
"""


def write(directory, name, source):
    (directory / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")


def load(tmp_path, **sources):
    for name, source in sources.items():
        write(tmp_path, name, source)
    return CarrierRegistry.load(tmp_path)


def test_load_reads_every_module(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, beta=BETA)
    snapshot = registry.current
    assert [module.code for module in snapshot.ordered()] == ["alpha", "beta"]
    assert snapshot.is_tracked("beta")
    assert not snapshot.is_tracked("alpha")
    assert snapshot.client("alpha") is None
    assert snapshot.display_name("alpha") == "Alpha & Co"
    assert snapshot.display_name("gone") == "gone"
    assert not snapshot.needs_phone("gone")
    assert registry.startup_rejections == []


def test_detect_keeps_highest_priority_and_orders_by_rank(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA, beta=BETA).current
    assert snapshot.detect("AL00000001") == Detection(("alpha",), False)
    assert snapshot.detect("000000000001") == Detection(("alpha", "beta"), False)
    assert snapshot.detect("BE00000001") == Detection(("beta",), True)
    assert snapshot.detect("nothing") == Detection()


def test_links_and_hints(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA, beta=BETA).current
    assert snapshot.link("alpha", "A#1") == "https://alpha.example/track?c=A%231"
    assert snapshot.link("beta", "X") is None
    assert snapshot.link("gone", "X") is None
    assert snapshot.pending_hint(("alpha", "beta"), "BE00000001") == "\nbeta hint"
    assert snapshot.pending_hint(("alpha",), "BE00000001") is None


def test_with_clients_replaces_clients_only(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA, beta=BETA).current
    fake = object()
    swapped = snapshot.with_clients({"beta": fake})
    assert swapped.client("beta") is fake
    assert swapped.is_tracked("beta")
    assert swapped.detect("AL00000001") == snapshot.detect("AL00000001")


def test_startup_skips_a_broken_module(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, broken="MODULE = 1 / 0\n")
    assert list(registry.current.modules) == ["alpha"]
    [rejection] = registry.startup_rejections
    assert rejection.code == "broken"
    assert rejection.error == "ZeroDivisionError line 1"


def test_syntax_error_reports_its_line(tmp_path):
    registry = load(tmp_path, broken="x = 1\nMODULE = (\n")
    assert registry.startup_rejections[0].error.startswith("SyntaxError line")


def test_module_code_must_match_file_name(tmp_path):
    registry = load(tmp_path, gamma=ALPHA)
    assert dict(registry.current.modules) == {}
    assert "must equal the file name" in registry.startup_rejections[0].error


def test_link_only_module_needs_https_link(tmp_path):
    registry = load(tmp_path, alpha=ALPHA.replace("https://alpha.example", "http://alpha.example"))
    assert "https link_template" in registry.startup_rejections[0].error


def test_rule_taking_another_carriers_codes_is_rejected(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, zeta=ZETA)
    assert list(registry.current.modules) == ["alpha"]
    [rejection] = registry.startup_rejections
    assert rejection.code == "zeta"
    assert "alpha: example AL00000001" in rejection.error


def test_examples_must_have_a_listed_code_length(tmp_path):
    anchor = '    examples=(("AL00000001", True),),\n'
    wrong = ALPHA.replace(anchor, anchor + "    code_lengths=(12,),\n")
    registry = load(tmp_path, alpha=wrong)
    assert dict(registry.current.modules) == {}
    assert "alpha: example AL00000001 has length 10" in registry.startup_rejections[0].error
    right = ALPHA.replace(anchor, anchor + "    code_lengths=(10, 12),\n")
    assert load(tmp_path, alpha=right).current.get("alpha").code_lengths == (10, 12)


def test_missing_directory_loads_nothing(tmp_path):
    registry = CarrierRegistry.load(tmp_path / "nope")
    assert dict(registry.current.modules) == {}


def test_refresh_waits_for_two_equal_reads_then_swaps(tmp_path):
    registry = load(tmp_path, alpha=ALPHA)
    write(tmp_path, "alpha", ALPHA.replace("Alpha & Co", "Alpha Two"))
    assert registry.refresh().reloaded == []
    assert registry.current.display_name("alpha") == "Alpha & Co"
    assert registry.refresh().reloaded == ["alpha"]
    assert registry.current.display_name("alpha") == "Alpha Two"
    assert registry.refresh().reloaded == []


def test_refresh_keeps_last_version_when_new_one_fails(tmp_path, caplog):
    registry = load(tmp_path, alpha=ALPHA)
    before = registry.current
    write(tmp_path, "alpha", ALPHA + "\nraise RuntimeError('boom')\n")
    registry.refresh()
    report = registry.refresh()
    assert registry.current is before
    [rejection] = report.rejected
    assert rejection.code == "alpha"
    assert rejection.error.startswith("RuntimeError line")
    assert registry.refresh().rejected == []
    assert registry.refresh().rejected == []
    assert "boom" not in caplog.text


def test_refresh_adds_new_module_and_keeps_deleted_one(tmp_path, caplog):
    registry = load(tmp_path, alpha=ALPHA)
    write(tmp_path, "beta", BETA)
    registry.refresh()
    assert registry.refresh().reloaded == ["beta"]
    assert registry.current.is_tracked("beta")
    (tmp_path / "alpha.py").unlink()
    registry.refresh()
    registry.refresh()
    assert registry.current.get("alpha") is not None
    assert caplog.text.count("carrier module file missing code=alpha") == 1


def test_refresh_rejects_rule_taking_another_carriers_codes(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, beta=BETA)
    stolen = BETA.replace(
        'Rule(r"BE[0-9A-Z]{8}", 10, standalone_only=True)', r'Rule(r"AL\d{8}", 200)'
    )
    write(tmp_path, "beta", stolen)
    registry.refresh()
    [rejection] = registry.refresh().rejected
    assert "alpha: example AL00000001" in rejection.error
    assert registry.current.detect("AL00000001").candidates == ("alpha",)


def test_broken_module_at_startup_is_added_once_fixed(tmp_path):
    registry = load(tmp_path, alpha=ALPHA, beta="MODULE = 1 / 0\n")
    assert registry.refresh().rejected == []
    write(tmp_path, "beta", BETA)
    registry.refresh()
    assert registry.refresh().reloaded == ["beta"]


def test_static_registry_refresh_does_nothing(tmp_path):
    snapshot = load(tmp_path, alpha=ALPHA).current
    assert CarrierRegistry(snapshot).refresh().reloaded == []


def test_progress_errors_are_contained_and_values_clamped(tmp_path):
    from datetime import UTC, datetime

    from vn_parcel_bot.carriers.models import TrackingEvent, TrackingResult

    event = TrackingEvent(time=datetime(2026, 9, 14, tzinfo=UTC), description="x")
    result = TrackingResult("alpha", "AL00000001", True, (event,))
    anchor = '    examples=(("AL00000001", True),),\n'
    broken = load(tmp_path, alpha=ALPHA.replace(anchor, anchor + "    progress=lambda r: 1 / 0,\n"))
    assert broken.current.progress("alpha", result) is None
    high = tmp_path / "high"
    high.mkdir()
    clamped = load(high, alpha=ALPHA.replace(anchor, anchor + "    progress=lambda r: 150,\n"))
    assert clamped.current.progress("alpha", result) == 100
