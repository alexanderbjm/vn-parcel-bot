import argparse
import importlib.util
import json
from pathlib import Path

import httpx
import respx

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "cainiao" / "in_transit.json"
CAINIAO_URL = "https://global.cainiao.com/global/detail.json"


def load_probe_module():
    spec = importlib.util.spec_from_file_location(
        "probe_carriers", ROOT / "scripts" / "probe_carriers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@respx.mock
async def test_parse_flag_prints_summary_without_body(tmp_path, monkeypatch, capsys):
    probe = load_probe_module()
    monkeypatch.setattr(probe, "RAW_DIR", tmp_path / "raw")

    async def no_pause():
        return None

    monkeypatch.setattr(probe, "pause", no_pause)
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    route = respx.get(url__startswith=CAINIAO_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )
    codes = tmp_path / "codes.txt"
    codes.write_text("cainiao LP00000000000001 in_transit\n", encoding="utf-8")

    await probe.probe_carriers(argparse.Namespace(file=str(codes), parse=True))

    out = capsys.readouterr().out
    assert route.call_count == 2
    assert "found=True" in out
    assert "events=4" in out
    assert "Đã đến trung tâm" not in out
    assert "LP00000000000001" not in out
    assert len(list((tmp_path / "raw").iterdir())) == 1


def test_spx_request_uses_order_info_endpoint():
    probe = load_probe_module()
    method, url, kwargs, kind = probe.build_request("spx", "SPXVN000000000001", None)
    assert (method, url, kind) == (
        "GET",
        "https://spx.vn/shipment/order/open/order/get_order_info",
        "json",
    )
    assert kwargs == {"params": {"language_code": "vi", "spx_tn": "SPXVN000000000001"}}


def test_spx_event_count_path():
    probe = load_probe_module()
    fixture = ROOT / "tests" / "fixtures" / "spx" / "in_transit.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert probe.event_count("spx", payload) == 8
