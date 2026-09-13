from datetime import timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.common import (
    clean_text,
    json_body,
    looks_like_challenge,
    parse_gmt_offset,
    request,
)
from vn_parcel_bot.carriers.models import CarrierError

URL = "https://carrier.example/track"
FIXTURES = Path(__file__).parent / "fixtures"
DEFAULT = timezone(timedelta(hours=3))


@respx.mock
async def test_request_returns_2xx_response():
    respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient() as http:
        response = await request(http, "cainiao", "GET", URL)
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    ("status", "reason"),
    [(403, "blocked"), (429, "blocked"), (500, "http_status"), (404, "http_status")],
)
@respx.mock
async def test_request_maps_blocked_and_http_status(status, reason):
    respx.get(URL).mock(return_value=httpx.Response(status, text="nope"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await request(http, "cainiao", "GET", URL)
    assert exc.value.reason == reason
    assert exc.value.carrier == "cainiao"
    assert exc.value.detail == str(status)


@respx.mock
async def test_request_not_found_status_passthrough():
    respx.get(URL).mock(return_value=httpx.Response(404, json={"error": {"code": 150002}}))
    async with httpx.AsyncClient() as http:
        response = await request(http, "ninjavan", "GET", URL, not_found_statuses=(404,))
    assert response.status_code == 404


@respx.mock
async def test_request_network_error():
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("t"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await request(http, "spx", "GET", URL)
    assert exc.value.reason == "network"
    assert exc.value.detail == "ConnectTimeout"


@respx.mock
async def test_request_challenge_page_blocked():
    body = '<script>document.cookie="D1N=1";window.location.reload(true);</script>'
    respx.get(URL).mock(
        return_value=httpx.Response(200, text=body, headers={"content-type": "text/html"})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await request(http, "viettelpost", "GET", URL)
    assert exc.value.reason == "blocked"


def test_json_body_html_blocked_and_text_parse():
    with pytest.raises(CarrierError) as html_exc:
        json_body("spx", httpx.Response(200, text="<html>"))
    assert html_exc.value.reason == "blocked"
    with pytest.raises(CarrierError) as text_exc:
        json_body("spx", httpx.Response(200, text="oops"))
    assert text_exc.value.reason == "parse"


def test_looks_like_challenge_cases():
    assert looks_like_challenge("<div class='g-recaptcha'></div>")
    assert looks_like_challenge("set x5sec cookie")
    assert looks_like_challenge("document.cookie='a=1'; window.location.reload()")
    jt_page = (FIXTURES / "jt" / "in_transit.html").read_text(encoding="utf-8")
    assert not looks_like_challenge(jt_page)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("GMT+8", timedelta(hours=8)),
        ("+07:00", timedelta(hours=7)),
        ("UTC-3", timedelta(hours=-3)),
        ("+0530", timedelta(hours=5, minutes=30)),
        (8, timedelta(hours=8)),
    ],
)
def test_parse_gmt_offset_cases(value, expected):
    assert parse_gmt_offset(value, DEFAULT).utcoffset(None) == expected


@pytest.mark.parametrize("value", [None, "abc", "GMT+99", True])
def test_parse_gmt_offset_defaults(value):
    assert parse_gmt_offset(value, DEFAULT) is DEFAULT


def test_clean_text():
    assert clean_text("  a \n b\t") == "a b"
