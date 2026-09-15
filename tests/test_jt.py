from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from bs4 import BeautifulSoup

from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.carriers.modules.jt import JT_TRACKING_URL, JtCarrier, parse_jt_html

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


JNTX_CODE = "JNTXB0000000001"


async def test_fetch_cross_border_without_phone_and_no_key_raises():
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError):
            await JtCarrier().fetch(http, JNTX_CODE, None)


async def test_fetch_standard_code_without_phone_raises_even_with_key():
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError):
            await JtCarrier(seventeen_key="key123").fetch(http, CODE, None)


@respx.mock
async def test_fetch_cross_border_without_phone_uses_17track():
    from vn_parcel_bot.carriers.seventeen_track import GET_TRACK_INFO_URL

    respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "accepted": [
                        {
                            "number": JNTX_CODE,
                            "carrier": 100295,
                            "latest_status": {"status": "InTransit"},
                            "track_info": {
                                "events": [
                                    {
                                        "time_utc": "2026-09-10T12:00:00Z",
                                        "description": "Rời kho Thâm Quyến",
                                        "location": "Shenzhen",
                                    }
                                ]
                            },
                        }
                    ],
                    "rejected": [],
                },
            },
        )
    )

    carrier = JtCarrier(seventeen_key="key123")
    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, JNTX_CODE, None)

    assert result.found is True
    assert result.carrier == "jt"
    assert result.tracking_number == JNTX_CODE
    assert len(result.events) == 1
    assert result.latest.description == "Rời kho Thâm Quyến"


@respx.mock
async def test_fetch_cross_border_domestic_not_found_falls_back_to_17track():
    from vn_parcel_bot.carriers.seventeen_track import GET_TRACK_INFO_URL

    respx.get(url__startswith=JT_TRACKING_URL).mock(
        return_value=httpx.Response(200, text=load_html("not_found"))
    )
    respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "accepted": [
                        {
                            "number": JNTX_CODE,
                            "carrier": 100295,
                            "latest_status": {"status": "InTransit"},
                            "track_info": {
                                "events": [
                                    {
                                        "time_utc": "2026-09-11T04:00:00Z",
                                        "description": "Đến cảng hàng không quốc tế",
                                    }
                                ]
                            },
                        }
                    ],
                    "rejected": [],
                },
            },
        )
    )

    carrier = JtCarrier(seventeen_key="key123")
    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, JNTX_CODE, "1234")

    assert result.found is True
    assert result.latest.description == "Đến cảng hàng không quốc tế"


@respx.mock
async def test_fetch_cross_border_merges_domestic_and_overseas():
    from vn_parcel_bot.carriers.seventeen_track import GET_TRACK_INFO_URL

    jntx_sample = "JNTX1234567890"
    html = load_html("in_transit").replace("840000000001", jntx_sample)
    respx.get(url__startswith=JT_TRACKING_URL).mock(return_value=httpx.Response(200, text=html))
    respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "accepted": [
                        {
                            "number": jntx_sample,
                            "carrier": 100295,
                            "latest_status": {"status": "InTransit"},
                            "track_info": {
                                "events": [
                                    {
                                        "time_utc": "2026-09-08T10:00:00Z",
                                        "description": "Xuất hàng từ Thâm Quyến",
                                        "location": "Shenzhen",
                                    }
                                ]
                            },
                        }
                    ],
                    "rejected": [],
                },
            },
        )
    )

    carrier = JtCarrier(seventeen_key="key123")
    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, jntx_sample, "1234")

    assert result.found is True
    # Has 4 domestic events + 1 overseas event = 5 events
    assert len(result.events) == 5
    assert result.events[0].description == "Xuất hàng từ Thâm Quyến"
    assert result.latest.description == "Đơn hàng đang được giao đến bạn"


BROKEN_JT_PAGE = "<html><body>maintenance</body></html>"


def jt_log(caplog) -> str:
    return " | ".join(
        r.getMessage() for r in caplog.records if r.name == "vn_parcel_bot.carriers.modules.jt"
    )


@respx.mock
async def test_17track_error_is_logged_when_jt_vn_also_fails(caplog):
    from vn_parcel_bot.carriers.seventeen_track import GET_TRACK_INFO_URL

    caplog.set_level("INFO")
    respx.get(url__startswith=JT_TRACKING_URL).mock(
        return_value=httpx.Response(200, text=BROKEN_JT_PAGE)
    )
    rejected = {"code": -18010012, "message": f"The tracking number {JNTX_CODE} is invalid."}
    respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"accepted": [], "rejected": [{"number": JNTX_CODE, "error": rejected}]},
            },
        )
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as raised:
            await JtCarrier(seventeen_key="key123").fetch(http, JNTX_CODE, "1234")
    assert raised.value.carrier == "jt"
    assert "17track" not in str(raised.value.detail)
    line = next(r for r in caplog.records if r.getMessage().startswith("17track error"))
    assert line.levelname == "WARNING"
    assert "reason=parse" in line.getMessage()
    assert JNTX_CODE not in jt_log(caplog)
    assert f"{JNTX_CODE[:5]}…{JNTX_CODE[-3:]}" in line.getMessage()


@respx.mock
async def test_empty_17track_answer_is_logged(caplog):
    from vn_parcel_bot.carriers.seventeen_track import GET_TRACK_INFO_URL, REGISTER_URL

    caplog.set_level("INFO")
    respx.get(url__startswith=JT_TRACKING_URL).mock(
        return_value=httpx.Response(200, text=BROKEN_JT_PAGE)
    )
    empty = {"code": 0, "data": {"accepted": [], "rejected": []}}
    respx.post(GET_TRACK_INFO_URL).mock(return_value=httpx.Response(200, json=empty))
    register = respx.post(REGISTER_URL).mock(return_value=httpx.Response(200, json=empty))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError):
            await JtCarrier(seventeen_key="key123").fetch(http, JNTX_CODE, "1234")
    assert register.called
    assert "17track no data carrier=jt" in jt_log(caplog)
    assert JNTX_CODE not in jt_log(caplog)


LIVE_PEOPLE = ("Nguyễn Văn A", "Trần Thị B", "Lê Văn C", "+849")


def test_parse_live_layout_reads_events_oldest_first():
    result = parse_jt_html(load_html("live_layout"), CODE)
    assert result.found
    times = [event.time for event in result.events]
    assert times == sorted(times)
    assert len(result.events) == 4
    assert result.events[0].time.isoformat() == "2026-09-13T18:12:45+07:00"
    assert result.latest.description == "Đơn hàng đã ký nhận."
    assert result.delivered
    assert not result.returned


def test_parse_live_layout_keeps_hubs_and_drops_people():
    result = parse_jt_html(load_html("live_layout"), CODE)
    described = [(event.description, event.location) for event in result.events]
    assert described == [
        ("Nhân viên của bưu cục (HNI) Kinh Doanh Mẫu đã nhận hàng.", "(HNI) Kinh Doanh Mẫu"),
        ("Bưu cục TTKT MẪU đang chuyển hàng đến (HNI) Bưu Cục Mẫu", "(HNI) Bưu Cục Mẫu"),
        ("Nhân viên của bưu cục (HNI) Bưu Cục Mẫu đang giao hàng.", "(HNI) Bưu Cục Mẫu"),
        ("Đơn hàng đã ký nhận.", None),
    ]
    for event in result.events:
        for person in LIVE_PEOPLE:
            assert person not in event.description
            assert person not in (event.location or "")


def test_parse_live_layout_ignores_another_bill():
    html = load_html("live_layout").replace(">840000000001<", ">840000000009<")
    with pytest.raises(CarrierError):
        parse_jt_html(html, CODE)
