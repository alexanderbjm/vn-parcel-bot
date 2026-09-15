import json
from dataclasses import replace

import httpx
import pytest
import respx

from vn_parcel_bot.agy_proxy import PROXY_HEADER, REREAD_HEADER
from vn_parcel_bot.services.vision_agy import AgyProxyVisionEngine, proxy_wait_seconds
from vn_parcel_bot.services.vision_engines import build_vision_engine
from vn_parcel_bot.tracking_codes import looks_misread

URL = "http://127.0.0.1:8765/read"
REPLY = json.dumps(
    {"tracking_codes": ["SPXVN000000000001"], "carrier": "SPX Express", "product_names": ["Ốp"]},
    ensure_ascii=False,
)


def reply(*codes: str) -> httpx.Response:
    return httpx.Response(200, json={"text": json.dumps({"tracking_codes": list(codes)})})


@pytest.fixture
def agy_settings(settings):
    return replace(settings, vision_engine="agy")


def test_build_vision_engine_picks_agy(agy_settings):
    engine = build_vision_engine(agy_settings, None)
    assert isinstance(engine, AgyProxyVisionEngine)
    assert engine.is_configured


def test_waits_for_both_models(agy_settings):
    assert proxy_wait_seconds(agy_settings) == 90 * 2 + 60


@respx.mock
async def test_posts_image_to_proxy_and_parses_reply(agy_settings):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"text": REPLY}))
    result = await AgyProxyVisionEngine(agy_settings).analyze_image(b"png-bytes", "image/png")
    assert result.error is None
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert result.carrier == "SPX Express"
    assert result.product_name == "Ốp"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.content == b"png-bytes"
    assert request.headers["Content-Type"] == "image/png"
    assert request.headers[PROXY_HEADER] == "1"
    assert REREAD_HEADER not in request.headers


@respx.mock
async def test_custom_proxy_url_and_unknown_media_type(agy_settings):
    route = respx.post("http://localhost:9000/read").mock(
        return_value=httpx.Response(200, json={"text": REPLY})
    )
    engine = AgyProxyVisionEngine(replace(agy_settings, agy_proxy_url="http://localhost:9000"))
    await engine.analyze_image(b"img", "image/tiff")
    assert route.calls.last.request.headers["Content-Type"] == "image/jpeg"


def test_looks_misread_uses_carrier_rules_and_lengths():
    assert not looks_misread("SPXVN000000000001")
    assert looks_misread("SPXVN00000000001")  # SPX codes have 17 characters
    assert looks_misread("12345678901")  # no carrier takes 11 digits
    assert not looks_misread("84000000000001")  # seller fleet code
    assert not looks_misread("GAN6DKKU12")  # carriers without code_lengths
    assert not looks_misread("SF0000000000001")


@respx.mock
async def test_rereads_once_when_a_code_has_the_wrong_length(agy_settings, caplog):
    caplog.set_level("INFO")
    route = respx.post(URL).mock(
        side_effect=[reply("SPXVN00000000001"), reply("SPXVN000000000001")]
    )
    result = await AgyProxyVisionEngine(agy_settings).analyze_image(b"img", "image/png")
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert route.call_count == 2
    assert REREAD_HEADER not in route.calls[0].request.headers
    assert route.calls[1].request.headers[REREAD_HEADER] == "1"
    assert route.calls[1].request.content == b"img"
    assert "reread used doubtful_codes=0" in caplog.text


@pytest.mark.parametrize(
    "second",
    [
        httpx.Response(200, json={"error": "timeout"}),
        reply(),
        reply("SPXVN0000000001", "12345678901"),
    ],
    ids=["error", "lost-the-code", "more-doubtful"],
)
@respx.mock
async def test_keeps_the_first_read_when_the_reread_is_not_better(agy_settings, second):
    route = respx.post(URL).mock(side_effect=[reply("SPXVN00000000001"), second])
    result = await AgyProxyVisionEngine(agy_settings).analyze_image(b"img", "image/png")
    assert result.error is None
    assert result.tracking_codes == ("SPXVN00000000001",)
    assert route.call_count == 2


@respx.mock
async def test_well_formed_codes_are_read_once(agy_settings):
    route = respx.post(URL).mock(return_value=reply("SPXVN000000000001", "GAN6DKKU12"))
    result = await AgyProxyVisionEngine(agy_settings).analyze_image(b"img", "image/png")
    assert result.tracking_codes == ("SPXVN000000000001", "GAN6DKKU12")
    assert route.call_count == 1


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("timeout", "timeout"),
        ("blocked", "blocked"),
        ("not_configured", "not_configured"),
        ("something-new", "cli_error"),
    ],
)
@respx.mock
async def test_proxy_errors(agy_settings, error, expected):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"error": error}))
    assert (await AgyProxyVisionEngine(agy_settings).analyze_image(b"img")).error == expected
    assert route.call_count == 1


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(403, json={"error": "forbidden"}), "http_status"),
        (httpx.Response(200, text="not json"), "invalid_response"),
        (httpx.Response(200, json=["list"]), "invalid_response"),
        (httpx.Response(200, json={"text": "  "}), "invalid_response"),
    ],
    ids=["status", "garbage", "not-object", "blank-text"],
)
@respx.mock
async def test_bad_proxy_responses(agy_settings, response, expected):
    respx.post(URL).mock(return_value=response)
    assert (await AgyProxyVisionEngine(agy_settings).analyze_image(b"img")).error == expected


@pytest.mark.parametrize(
    ("exc", "expected"),
    [(httpx.ConnectError("refused"), "network"), (httpx.ReadTimeout("slow"), "timeout")],
    ids=["proxy-down", "slow"],
)
@respx.mock
async def test_transport_failures(agy_settings, exc, expected):
    respx.post(URL).mock(side_effect=exc)
    assert (await AgyProxyVisionEngine(agy_settings).analyze_image(b"img")).error == expected


@respx.mock
async def test_logs_hold_no_reply_text(agy_settings, caplog):
    caplog.set_level("DEBUG")
    respx.post(URL).mock(
        side_effect=[reply("SPXVN00000000001"), httpx.Response(200, json={"text": REPLY})]
    )
    await AgyProxyVisionEngine(agy_settings).analyze_image(b"img")
    assert "SPXVN0000000000" not in caplog.text
    assert "Ốp" not in caplog.text
