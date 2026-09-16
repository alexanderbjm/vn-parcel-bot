import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.carriers.seventeen_track import (
    ERR_ALREADY_REGISTERED,
    ERR_NOT_REGISTERED,
    ERR_QUOTA_EXCEEDED,
    GET_TRACK_INFO_URL,
    REGISTER_URL,
    SeventeenTrackCarrier,
)

CARRIER_ID = 101194  # BEST Inc (VN)
API_KEY = "test-token-12345"
CODE = "BEST0000000001"


def make_carrier(
    carrier_code: str = "best",
    carrier_id: int = CARRIER_ID,
    key: str = API_KEY,
) -> SeventeenTrackCarrier:
    return SeventeenTrackCarrier(
        carrier_code=carrier_code,
        display_name="BEST Express",
        seventeen_carrier_id=carrier_id,
        api_key=key,
    )


def track_info_response(
    tracking_number: str,
    status: str = "InTransit",
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if events is None:
        events = [
            {
                "time_utc": "2026-09-12T10:00:00Z",
                "description": "Bưu cục nhận hàng",
                "location": "Hà Nội",
                "stage": "Transit",
            }
        ]
    return {
        "code": 0,
        "data": {
            "accepted": [
                {
                    "number": tracking_number,
                    "carrier": CARRIER_ID,
                    "latest_status": {"status": status},
                    "track_info": {
                        "events": events,
                    },
                }
            ],
            "rejected": [],
        },
    }


def track_info_rejected(
    tracking_number: str,
    err_code: int,
    message: str = "",
) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "accepted": [],
            "rejected": [
                {
                    "number": tracking_number,
                    "error": {"code": err_code, "message": message},
                }
            ],
        },
    }


@respx.mock
async def test_fetch_query_first_success():
    carrier = make_carrier()
    route = respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(200, json=track_info_response(CODE, "InTransit"))
    )

    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE)

    assert route.call_count == 1
    req = route.calls.last.request
    assert req.headers["17token"] == API_KEY
    assert result.found is True
    assert result.carrier == "best"
    assert result.tracking_number == CODE
    assert len(result.events) == 1
    assert result.latest.description == "Bưu cục nhận hàng"
    assert result.latest.location == "Hà Nội"
    assert result.latest.time == datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    assert result.delivered is False
    assert result.returned is False


@respx.mock
async def test_fetch_auto_registers_when_not_registered():
    carrier = make_carrier()
    # 1st call: not registered (-18019902)
    # 2nd call: register returns success
    # 3rd call: gettrackinfo returns tracking data
    info_route = respx.post(GET_TRACK_INFO_URL)
    info_route.side_effect = [
        httpx.Response(200, json=track_info_rejected(CODE, ERR_NOT_REGISTERED, "Not registered")),
        httpx.Response(200, json=track_info_response(CODE, "Delivered")),
    ]
    reg_route = respx.post(REGISTER_URL).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"accepted": [{"number": CODE}]}})
    )

    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE)

    assert info_route.call_count == 2
    assert reg_route.call_count == 1
    assert result.found is True
    assert result.delivered is True
    assert result.returned is False


@respx.mock
async def test_fetch_auto_register_disabled_returns_not_found():
    carrier = make_carrier()
    info_route = respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(
            200, json=track_info_rejected(CODE, ERR_NOT_REGISTERED, "Not registered")
        )
    )
    reg_route = respx.post(REGISTER_URL).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {}})
    )

    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE, auto_register=False)

    assert info_route.call_count == 1
    assert reg_route.call_count == 0
    assert result.found is False


@respx.mock
async def test_fetch_register_already_registered_ignored():
    carrier = make_carrier()
    info_route = respx.post(GET_TRACK_INFO_URL)
    info_route.side_effect = [
        httpx.Response(200, json=track_info_rejected(CODE, ERR_NOT_REGISTERED)),
        httpx.Response(200, json=track_info_response(CODE, "Returned")),
    ]
    respx.post(REGISTER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"rejected": [{"number": CODE, "error": {"code": ERR_ALREADY_REGISTERED}}]},
            },
        )
    )

    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE)

    assert result.found is True
    assert result.returned is True
    assert result.delivered is False


@respx.mock
async def test_fetch_quota_exceeded_on_query_raises_blocked():
    carrier = make_carrier()
    respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(
            200,
            json=track_info_rejected(CODE, ERR_QUOTA_EXCEEDED, "Quota exceeded"),
        )
    )

    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await carrier.fetch(http, CODE)

    assert exc.value.reason == "blocked"
    assert "quota" in exc.value.detail.lower()


@respx.mock
async def test_fetch_quota_exceeded_on_register_raises_blocked():
    carrier = make_carrier()
    respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(200, json=track_info_rejected(CODE, ERR_NOT_REGISTERED))
    )
    respx.post(REGISTER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"rejected": [{"number": CODE, "error": {"code": ERR_QUOTA_EXCEEDED}}]},
            },
        )
    )

    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await carrier.fetch(http, CODE)

    assert exc.value.reason == "blocked"
    assert "quota" in exc.value.detail.lower()


@respx.mock
async def test_fetch_providers_nested_structure():
    carrier = make_carrier()
    payload = {
        "code": 0,
        "data": {
            "accepted": [
                {
                    "number": CODE,
                    "latest_status": {"status": "InTransit"},
                    "track_info": {
                        "providers": [
                            {
                                "events": [
                                    {
                                        "time_iso": "2026-09-11T08:00:00+07:00",
                                        "description": "Lấy hàng thành công",
                                        "location": "Bưu cục",
                                    }
                                ]
                            }
                        ]
                    },
                }
            ]
        },
    }
    respx.post(GET_TRACK_INFO_URL).mock(return_value=httpx.Response(200, json=payload))

    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE)

    assert result.found is True
    assert len(result.events) == 1
    assert result.latest.description == "Lấy hàng thành công"
    assert result.latest.location == "Bưu cục"


def documented_payload(latest_status, events):
    return {
        "code": 0,
        "data": {
            "accepted": [
                {
                    "number": CODE,
                    "carrier": CARRIER_ID,
                    "track_info": {
                        "latest_status": latest_status,
                        "tracking": {"providers": [{"events": events}]},
                    },
                }
            ],
            "rejected": [],
        },
    }


@respx.mock
async def test_fetch_reads_documented_track_info_nesting():
    events = [
        {
            "time_utc": "2026-09-12T10:00:00Z",
            "description": "Giao hàng thành công",
            "location": "HCM",
        },
        {"time_utc": "2026-09-11T10:00:00Z", "description": "Đang vận chuyển", "location": None},
    ]
    payload = documented_payload({"status": "Delivered", "sub_status": "Delivered_Other"}, events)
    respx.post(GET_TRACK_INFO_URL).mock(return_value=httpx.Response(200, json=payload))

    async with httpx.AsyncClient() as http:
        result = await make_carrier().fetch(http, CODE)

    assert result.found is True
    assert result.delivered is True
    assert result.returned is False
    assert [event.description for event in result.events] == [
        "Đang vận chuyển",
        "Giao hàng thành công",
    ]
    assert result.events[0].location is None


@respx.mock
async def test_phone_digits_ride_along_on_query_and_register():
    carrier = make_carrier()
    info_route = respx.post(GET_TRACK_INFO_URL)
    info_route.side_effect = [
        httpx.Response(200, json=track_info_rejected(CODE, ERR_NOT_REGISTERED, "Not registered")),
        httpx.Response(200, json=track_info_response(CODE, "InTransit")),
    ]
    reg_route = respx.post(REGISTER_URL).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"accepted": [{"number": CODE}]}})
    )

    async with httpx.AsyncClient() as http:
        result = await carrier.fetch(http, CODE, "4567")

    assert result.found is True
    expected = [{"number": CODE, "carrier": CARRIER_ID, "phone_number_last_4": "4567"}]
    assert json.loads(info_route.calls[0].request.content) == expected
    assert json.loads(reg_route.calls.last.request.content) == expected
    assert json.loads(info_route.calls.last.request.content) == expected


@respx.mock
async def test_phone_field_is_absent_when_no_digits_are_known():
    carrier = make_carrier()
    route = respx.post(GET_TRACK_INFO_URL).mock(
        return_value=httpx.Response(200, json=track_info_response(CODE, "InTransit"))
    )

    async with httpx.AsyncClient() as http:
        await carrier.fetch(http, CODE)

    assert json.loads(route.calls.last.request.content) == [{"number": CODE, "carrier": CARRIER_ID}]


@respx.mock
async def test_fetch_exception_returned_sub_status_is_returned():
    events = [{"time_utc": "2026-09-12T10:00:00Z", "description": "Hoàn hàng", "location": "HN"}]
    payload = documented_payload(
        {"status": "Exception", "sub_status": "Exception_Returned"}, events
    )
    respx.post(GET_TRACK_INFO_URL).mock(return_value=httpx.Response(200, json=payload))

    async with httpx.AsyncClient() as http:
        result = await make_carrier().fetch(http, CODE)

    assert result.returned is True
    assert result.delivered is False
