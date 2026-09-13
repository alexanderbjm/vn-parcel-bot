from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from vn_parcel_bot.carriers.jt import JT_TRACKING_URL, JtCarrier, parse_jt_html
from vn_parcel_bot.carriers.models import CarrierError

FIXTURES = Path(__file__).parent / "fixtures" / "jt"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "840000000001"


def load_html(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def test_parse_in_transit():
    result = parse_jt_html(load_html("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("jt", CODE)
    assert len(result.events) == 4
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert all(t.utcoffset() is not None for t in times)
    assert result.latest.description == "Đơn hàng đang được giao đến bạn"
    assert result.latest.location == "Bưu cục Quận 7"
    assert result.events[0].location is None
    assert not result.delivered
    assert not result.returned


def test_parse_delivered():
    result = parse_jt_html(load_html("delivered"), "840000000002")
    assert result.delivered is True
    assert result.returned is False


def test_parse_returned_marker():
    html = load_html("in_transit").replace(
        "Đơn hàng đang được giao đến bạn", "Hoàn hàng thành công"
    )
    result = parse_jt_html(html, CODE)
    assert result.returned is True
    assert result.delivered is False


def test_parse_not_found_fixture():
    assert parse_jt_html(load_html("not_found"), CODE).found is False


def test_parse_not_found_marker_minimal():
    html = "<html><body><p>Không tìm thấy dữ liệu về vận đơn</p></body></html>"
    assert parse_jt_html(html, CODE).found is False


def test_parse_empty_vandon_minimal():
    assert parse_jt_html('<div class="empty-vandon"></div>', CODE).found is False


def test_parse_unknown_page_raises():
    with pytest.raises(CarrierError) as exc:
        parse_jt_html("<html><body>Bảo trì hệ thống</body></html>", CODE)
    assert exc.value.reason == "parse"


def test_parse_event_missing_time_raises():
    soup = BeautifulSoup(load_html("in_transit"), "html.parser")
    soup.select_one(".event-time").decompose()
    with pytest.raises(CarrierError) as exc:
        parse_jt_html(str(soup), CODE)
    assert exc.value.reason == "parse"


def test_parse_unparseable_time_raises():
    html = load_html("in_transit").replace("11/09/2026 08:15", "hôm nay")
    with pytest.raises(CarrierError) as exc:
        parse_jt_html(html, CODE)
    assert exc.value.reason == "parse"


def test_parse_picks_matching_bill_block():
    html = """
    <div class="result-tracking">
      <div class="tracking-bill" data-billcode="840000000009">
        <li class="tracking-event"><span class="event-time">09/09/2026 10:00</span>
        <span class="event-desc">Đơn khác</span></li>
      </div>
      <div class="tracking-bill" data-billcode="840000000001">
        <li class="tracking-event"><span class="event-time">10/09/2026 10:00:30</span>
        <span class="event-desc">Đơn của tôi</span></li>
      </div>
    </div>"""
    result = parse_jt_html(html, CODE)
    assert [e.description for e in result.events] == ["Đơn của tôi"]
    assert result.latest.time.astimezone(VN).second == 30


def test_parse_oldest_event_local_time():
    result = parse_jt_html(load_html("in_transit"), CODE)
    assert result.events[0].time.astimezone(VN).strftime("%d/%m %H:%M") == "10/09 09:30"


async def test_fetch_requires_phone():
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError):
            await JtCarrier().fetch(http, CODE, None)


@respx.mock
async def test_fetch_sends_code_and_digits():
    route = respx.get(url__startswith=JT_TRACKING_URL).mock(
        return_value=httpx.Response(200, text=load_html("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await JtCarrier().fetch(http, CODE, "1234")
    params = route.calls.last.request.url.params
    assert (params["billcode"], params["cellphone"], params["type"]) == (CODE, "1234", "track")
    assert result.found


@pytest.mark.parametrize(
    ("status", "reason"),
    [(403, "blocked"), (429, "blocked"), (500, "http_status"), (404, "http_status")],
)
@respx.mock
async def test_fetch_maps_http_errors(status, reason):
    respx.get(url__startswith=JT_TRACKING_URL).mock(return_value=httpx.Response(status))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await JtCarrier().fetch(http, CODE, "1234")
    assert exc.value.reason == reason


@respx.mock
async def test_fetch_network_error():
    respx.get(url__startswith=JT_TRACKING_URL).mock(side_effect=httpx.ReadTimeout("t"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await JtCarrier().fetch(http, CODE, "1234")
    assert exc.value.reason == "network"


@respx.mock
async def test_fetch_challenge_page_blocked():
    respx.get(url__startswith=JT_TRACKING_URL).mock(
        return_value=httpx.Response(200, text="<html>captcha</html>")
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await JtCarrier().fetch(http, CODE, "1234")
    assert exc.value.reason == "blocked"


def test_carrier_attributes():
    carrier = JtCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == ("jt", "J&T", True)
