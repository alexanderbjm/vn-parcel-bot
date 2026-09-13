import json
import re
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = {
    "spx": ["in_transit.json", "delivered.json", "not_found.json"],
    "jt": ["in_transit.html", "delivered.html", "not_found.html"],
    "cainiao": ["in_transit.json", "delivered.json", "not_found.json"],
    "fourpx": ["in_transit.json", "delivered.json", "not_found.json"],
    "ninjavan": ["in_transit.json", "delivered.json", "returned.json", "not_found.json"],
    "ghn": ["in_transit.json", "delivered.json", "not_found.json"],
}
CODE_RE = re.compile(r"SPXVN\d+|SPEVN\d+|LP\d{14}|4PX\d{16}|GA\d{10}|(?<!\d)84\d{10}(?!\d)")
FAKE_RE = re.compile(r"^(SPXVN|SPEVN|LP|4PX|GA|84)0*[0-3]$")


def fixture_files():
    return [p for p in FIXTURES.glob("*/*") if not p.parent.name.startswith("_")]


def test_every_json_fixture_parses():
    for path in FIXTURES.glob("*/*.json"):
        if not path.parent.name.startswith("_"):
            json.loads(path.read_text(encoding="utf-8"))


def test_fixture_set_complete():
    for carrier, names in EXPECTED.items():
        for name in names:
            assert (FIXTURES / carrier / name).is_file(), f"{carrier}/{name}"


def test_fixtures_documented():
    doc = (FIXTURES / "FIXTURES.md").read_text(encoding="utf-8")
    for carrier, names in EXPECTED.items():
        for name in names:
            assert f"{carrier}/{name}" in doc


def test_fixture_codes_are_fake():
    for path in fixture_files():
        text = path.read_text(encoding="utf-8")
        for code in CODE_RE.findall(text):
            assert FAKE_RE.match(code), f"{path.name}: {code}"
