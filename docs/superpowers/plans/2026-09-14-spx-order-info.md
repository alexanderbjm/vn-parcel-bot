# SPX order-info endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SPX parcels track again by reading the endpoint spx.vn's own tracking page uses (`get_order_info`), replacing the dead `fleet_order/tracking/search` request and its signing code.

**Architecture:** `carriers/spx.py` stays a plain `httpx` carrier like Cainiao: `SpxCarrier.fetch` sends one GET through the shared `request()` helper and `parse_spx_response` turns `data.sls_tracking_info.records` into `TrackingEvent`s, keeping only the records spx.vn shows publicly (`display_flag == 1`) and never touching the personal fields in the same response. Fixtures and the probe script follow the new shape.

**Tech Stack:** Python 3.13, httpx, respx, pytest (asyncio auto mode), ruff (line length 100), PowerShell 5.1 on Windows.

**Spec:** `docs/superpowers/specs/2026-09-14-spx-browser-vision-digests-design.md` §3 and §6

## Global Constraints

- Run tools through the venv: `.\.venv\Scripts\python -m pytest …`, `.\.venv\Scripts\python -m ruff …`.
- No browser, no Playwright, no request signing, no page-generated headers, no user-agent spoofing. Blocks surface as `CarrierError` (`blocked`, `http_status`, `network`, `parse`) through the existing `request()`/`json_body()` helpers.
- Personal fields in SPX responses (`receiver_name`, `driver_phone_number`, `client_order_id`, `buyer_description`, `epod`, `full_address`, `lat`, `lng`, `next_location`) are never read into events, logged, stored or put in fixtures with real values.
- No real tracking codes in any committed file. Real codes live only in `probe_codes.local.txt` and `data/` (both git-ignored); raw probe captures go to `tests/fixtures/_raw/` (git-ignored).
- Branch `build/v1`. Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN
  ```
- Leave agy's uncommitted changes in `src/vn_parcel_bot/config.py` and `src/vn_parcel_bot/services/vision.py` untouched and unstaged (they belong to Part B). Stage files by explicit path only.
- Gates before every commit: `ruff check .`, `ruff format --check .`, full `pytest` green.

---

### Task 1: SPX adapter on the order-info endpoint

**Files:**
- Replace: `tests/fixtures/spx/in_transit.json`, `tests/fixtures/spx/delivered.json`, `tests/fixtures/spx/not_found.json`
- Modify: `tests/fixtures/FIXTURES.md` (the `## SPX Express Vietnam` section only)
- Replace: `tests/test_spx.py`
- Replace: `src/vn_parcel_bot/carriers/spx.py`
- Modify: `scripts/probe_carriers.py` (imports, `build_request`, `event_count`, `parse_summary`, `probe_carriers`, `main`)
- Modify: `tests/test_probe_script.py`

**Interfaces:**
- Consumes: `vn_parcel_bot.carriers.common.request(http, carrier, method, url, **kwargs) -> httpx.Response`, `json_body(carrier, response) -> Any`, `clean_text(value) -> str`; `TrackingEvent`, `TrackingResult`, `CarrierError` from `carriers.models`.
- Produces: `SPX_ORDER_INFO_URL: str`, `NOT_FOUND_RETCODES: tuple[int, ...]`, `parse_spx_response(payload: object, tracking_number: str) -> TrackingResult`, `SpxCarrier()` (no constructor arguments) with `async fetch(http, tracking_number, phone_last4=None) -> TrackingResult`; probe `build_request(carrier, code, last4) -> tuple[str, str, dict[str, Any], str]` and `parse_summary(http, carrier, code, last4) -> str`.

- [ ] **Step 1: Replace the SPX fixtures**

`tests/fixtures/spx/in_transit.json`:

```json
{
  "retcode": 0,
  "message": "success",
  "detail": "",
  "debug": "",
  "data": {
    "fulfillment_info": {"deliver_type": 1},
    "is_instant_order": false,
    "is_shopee_market_order": true,
    "sls_tracking_info": {
      "sls_tn": "SPXVN000000000001",
      "client_order_id": "000000000000001",
      "receiver_name": "N***A",
      "receiver_type_name": "",
      "driver_phone_number": "0900000000",
      "records": [
        {
          "tracking_code": "F600", "tracking_name": "Out For Delivery",
          "description": "Đang giao hàng", "display_flag": 1, "display_flag_v2": 13,
          "actual_time": 1789084860, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "Giao cho N***A tại Số 1 Đường Giả",
          "seller_description": "Đơn hàng chuẩn bị giao tới người mua",
          "milestone_code": 6, "milestone_name": "Out for delivery"
        },
        {
          "tracking_code": "F598", "tracking_name": "Delivery Driver Assigned",
          "description": "Đã sắp xếp tài xế giao hàng", "display_flag": 0, "display_flag_v2": 5,
          "actual_time": 1789084800, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "Đã sắp xếp tài xế giao hàng",
          "milestone_code": 5, "milestone_name": "In transit"
        },
        {
          "tracking_code": "F599", "tracking_name": "Enter Last Mile Hub",
          "description": "Đơn hàng đã đến kho 50-HCM Quan 1 Hub", "display_flag": 1, "display_flag_v2": 13,
          "actual_time": 1789063200, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "50-HCM Quan 1 Hub", "location_type_name": "", "lng": "106.000000", "lat": "10.000000", "full_address": "Số 1 Đường Giả, Quận 1"},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "Đơn hàng đã đến kho 50-HCM Quan 1 Hub",
          "milestone_code": 5, "milestone_name": "In transit"
        },
        {
          "tracking_code": "F540", "tracking_name": "Left Domestic Sorting Center",
          "description": "Đơn hàng đang được trung chuyển  tới 50-HCM Quan 1 Hub", "display_flag": 0, "display_flag_v2": 5,
          "actual_time": 1789027200, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "50-HCM Quan 1 Hub", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "Đơn hàng đang được trung chuyển",
          "milestone_code": 5, "milestone_name": "In transit"
        },
        {
          "tracking_code": "F510", "tracking_name": "Enter Domestic Sorting Center",
          "description": "Đơn hàng đã đến kho SOC Ho Chi Minh", "display_flag": 1, "display_flag_v2": 13,
          "actual_time": 1789020000, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "SOC Ho Chi Minh", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "Đơn hàng đã đến kho SOC Ho Chi Minh",
          "milestone_code": 5, "milestone_name": "In transit"
        },
        {
          "tracking_code": "F100", "tracking_name": "Pickup From Domestic Seller",
          "description": "Đơn vị vận chuyển lấy hàng thành công", "display_flag": 1, "display_flag_v2": 13,
          "actual_time": 1789005600, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "Đơn vị vận chuyển lấy hàng thành công",
          "milestone_code": 5, "milestone_name": "In transit"
        },
        {
          "tracking_code": "F000", "tracking_name": "Manifested",
          "description": " Người bán đang chuẩn bị hàng", "display_flag": 1, "display_flag_v2": 13,
          "actual_time": 1788998460, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "Người bán đang chuẩn bị hàng",
          "milestone_code": 1, "milestone_name": "Preparing to ship"
        },
        {
          "tracking_code": "A000", "tracking_name": "SLSTN Created",
          "description": "SLSTN đã được tạo, đang gửi yêu cầu đến đối tác vận chuyển", "display_flag": 0, "display_flag_v2": 0,
          "actual_time": 1788998400, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "", "seller_description": "",
          "milestone_code": 1, "milestone_name": "Preparing to ship"
        }
      ]
    }
  }
}
```

`tests/fixtures/spx/delivered.json`: identical to `in_transit.json` except `"sls_tn": "SPXVN000000000002"`, `"client_order_id": "000000000000002"`, and one extra record inserted **first** in `records`:

```json
        {
          "tracking_code": "F980", "tracking_name": "Delivered",
          "description": "Giao hàng thành công", "display_flag": 1, "display_flag_v2": 13,
          "actual_time": 1789095600, "reason_code": "R00", "reason_desc": "R00", "epod": "",
          "current_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "next_location": {"location_name": "", "location_type_name": "", "lng": "", "lat": "", "full_address": ""},
          "buyer_description": "Đã giao cho N***A tại Số 1 Đường Giả",
          "seller_description": "Giao hàng thành công",
          "milestone_code": 8, "milestone_name": "Delivered"
        },
```

`tests/fixtures/spx/not_found.json`:

```json
{
  "retcode": 2,
  "message": "retcode:-2023002, message:executeStandardApiStep:executeStandardApiFunc StepIndex[1]:execute func,FuncName[GetLogisticOrderIndexMap]:ref record not unique,find [0]:get logistic order index map error",
  "detail": "",
  "debug": "",
  "data": {}
}
```

Timestamps: `1788998400` = 2026-09-10 00:00 UTC (07:00 in Vietnam); `1788998460` → 10/09 07:01; `1789005600` → 10/09 09:00; `1789020000` → 10/09 13:00; `1789063200` → 11/09 01:00; `1789084860` → 11/09 07:01; `1789095600` → 11/09 10:00 (all Vietnam time).

- [ ] **Step 2: Rewrite the SPX section of `tests/fixtures/FIXTURES.md`**

Replace everything from `## SPX Express Vietnam` up to (not including) `## J&T Express Vietnam` with:

```markdown
## SPX Express Vietnam

- Provenance: **synthetic 2026-09-14**, shaped like a live `get_order_info` response captured for a real code the same day (values invented; personal fields are placeholders)
- Request: `GET https://spx.vn/shipment/order/open/order/get_order_info?language_code=vi&spx_tn=<code>`
- Paths: `retcode`; `data.sls_tracking_info.records[]` (newest first) → `actual_time` (Unix seconds, UTC), `description`, `tracking_code`, `milestone_code`, `display_flag`, `current_location.location_name`
- Not found: `{"retcode": 2, "message": "…find [0]…", "data": {}}` (observed 2026-09-14 for an unknown code)
- Only `display_flag: 1` records become events; `in_transit.json` has 8 records, 5 shown
- Delivered: latest shown record `tracking_code` `F980` / `milestone_code` 8; returned marker: none in these files
- Personal placeholders that must never appear in events: `receiver_name` `N***A`, `driver_phone_number` `0900000000`, `buyer_description` mentioning `Đường Giả`, coordinates `10.000000` / `106.000000`
- The oldest shown description has a leading space (`" Người bán đang chuẩn bị hàng"`), parsed without it

| File | Code | Events | Latest description | Oldest local |
|---|---|---|---|---|
| `spx/in_transit.json` | `SPXVN000000000001` | 5 | Đang giao hàng | 10/09 07:01 |
| `spx/delivered.json` | `SPXVN000000000002` | 6 | Giao hàng thành công | 10/09 07:01 |
| `spx/not_found.json` | – | 0 | – | – |

```

- [ ] **Step 3: Write the failing tests** — replace `tests/test_spx.py` with:

```python
import copy
import json
from datetime import UTC, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from vn_parcel_bot.carriers.models import CarrierError
from vn_parcel_bot.carriers.spx import SPX_ORDER_INFO_URL, SpxCarrier, parse_spx_response

FIXTURES = Path(__file__).parent / "fixtures" / "spx"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
CODE = "SPXVN000000000001"
DELIVERED_CODE = "SPXVN000000000002"


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def records(payload: dict) -> list[dict]:
    return payload["data"]["sls_tracking_info"]["records"]


def test_parse_in_transit():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert result.found
    assert (result.carrier, result.tracking_number) == ("spx", CODE)
    assert len(result.events) == 5
    times = [e.time for e in result.events]
    assert times == sorted(times)
    assert all(t.utcoffset() == timedelta(0) for t in times)
    assert result.latest.description == "Đang giao hàng"
    assert result.latest.raw_status == "F600"
    assert not result.delivered
    assert not result.returned


def test_parse_skips_internal_records():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert [e.raw_status for e in result.events] == ["F000", "F100", "F510", "F599", "F600"]


def test_parse_collapses_whitespace_and_keeps_local_time():
    oldest = parse_spx_response(load_json("in_transit"), CODE).events[0]
    assert oldest.description == "Người bán đang chuẩn bị hàng"
    assert oldest.time.astimezone(VN).strftime("%d/%m %H:%M") == "10/09 07:01"


def test_parse_location_only_when_not_in_description():
    result = parse_spx_response(load_json("in_transit"), CODE)
    assert all(e.location is None for e in result.events)
    payload = load_json("in_transit")
    records(payload)[0]["current_location"]["location_name"] = "  Bưu cục  Quận 1 "
    assert parse_spx_response(payload, CODE).latest.location == "Bưu cục Quận 1"


def test_parse_never_exposes_personal_fields():
    result = parse_spx_response(load_json("delivered"), DELIVERED_CODE)
    shown = " ".join(
        f"{e.description} {e.location or ''} {e.raw_status or ''}" for e in result.events
    )
    for private in ("N***A", "0900000000", "Đường Giả", "10.000000", "000000000000002"):
        assert private not in shown


def test_parse_delivered_by_tracking_code():
    result = parse_spx_response(load_json("delivered"), DELIVERED_CODE)
    assert len(result.events) == 6
    assert result.latest.description == "Giao hàng thành công"
    assert result.latest.raw_status == "F980"
    assert result.delivered is True
    assert result.returned is False


def test_parse_delivered_by_milestone():
    payload = load_json("delivered")
    records(payload)[0]["tracking_code"] = "F981"
    assert parse_spx_response(payload, DELIVERED_CODE).delivered is True


def test_parse_returned_marker():
    payload = load_json("in_transit")
    records(payload)[0].update(
        tracking_code="F999",
        tracking_name="Return To Seller",
        description="Đơn hàng đang được hoàn hàng",
        milestone_code=9,
        milestone_name="Returning",
    )
    result = parse_spx_response(payload, CODE)
    assert result.returned is True
    assert result.delivered is False


def test_parse_not_found_retcode():
    result = parse_spx_response(load_json("not_found"), CODE)
    assert result.found is False
    assert result.events == ()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(data={}),
        lambda p: p["data"].pop("sls_tracking_info"),
        lambda p: p["data"]["sls_tracking_info"].update(records=[]),
        lambda p: [r.update(display_flag=0) for r in records(p)],
    ],
    ids=["empty-data", "no-tracking-info", "empty-records", "only-internal-records"],
)
def test_parse_not_found_shapes(mutate):
    payload = load_json("in_transit")
    mutate(payload)
    assert parse_spx_response(payload, CODE).found is False


@pytest.mark.parametrize("payload", [[], "x", {"message": "no retcode"}])
def test_parse_rejects_unexpected_payload(payload):
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


def test_parse_unknown_retcode():
    with pytest.raises(CarrierError) as exc:
        parse_spx_response({"retcode": 99999, "message": "x", "data": {}}, CODE)
    assert exc.value.reason == "parse"
    assert "99999" in exc.value.detail


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["data"].update(sls_tracking_info="x"),
        lambda p: p["data"]["sls_tracking_info"].update(records="x"),
    ],
    ids=["tracking-info-not-object", "records-not-list"],
)
def test_parse_rejects_malformed_structure(mutate):
    payload = load_json("in_transit")
    mutate(payload)
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


@pytest.mark.parametrize(
    "item",
    [
        "not an object",
        {"display_flag": 1, "description": "no time"},
        {"display_flag": 1, "actual_time": True, "description": "bool time"},
        {"display_flag": 1, "actual_time": "1789084860", "description": "text time"},
        {"display_flag": 1, "actual_time": 1789084860},
        {"display_flag": 1, "actual_time": 1789084860, "description": "   "},
    ],
)
def test_parse_rejects_bad_records(item):
    payload = copy.deepcopy(load_json("in_transit"))
    records(payload).append(item)
    with pytest.raises(CarrierError) as exc:
        parse_spx_response(payload, CODE)
    assert exc.value.reason == "parse"


@respx.mock
async def test_fetch_sends_code_and_language():
    route = respx.get(url__startswith=SPX_ORDER_INFO_URL).mock(
        return_value=httpx.Response(200, json=load_json("in_transit"))
    )
    async with httpx.AsyncClient() as http:
        result = await SpxCarrier().fetch(http, CODE)
    assert result.found
    params = route.calls.last.request.url.params
    assert params["spx_tn"] == CODE
    assert params["language_code"] == "vi"


@pytest.mark.parametrize(
    ("status", "text", "reason"),
    [
        (403, "", "blocked"),
        (429, "", "blocked"),
        (500, "", "http_status"),
        (200, "<html>captcha</html>", "blocked"),
    ],
)
@respx.mock
async def test_fetch_maps_errors(status, text, reason):
    respx.get(url__startswith=SPX_ORDER_INFO_URL).mock(
        return_value=httpx.Response(status, text=text)
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await SpxCarrier().fetch(http, CODE)
    assert exc.value.reason == reason
    assert exc.value.carrier == "spx"


@respx.mock
async def test_fetch_network_error():
    respx.get(url__startswith=SPX_ORDER_INFO_URL).mock(side_effect=httpx.ConnectTimeout("t"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(CarrierError) as exc:
            await SpxCarrier().fetch(http, CODE)
    assert exc.value.reason == "network"


def test_carrier_attributes():
    carrier = SpxCarrier()
    assert (carrier.code, carrier.display_name, carrier.needs_phone) == ("spx", "SPX", False)


def test_event_times_are_utc_aware():
    result = parse_spx_response(load_json("delivered"), DELIVERED_CODE)
    assert result.latest.time.tzinfo is UTC
```

In `tests/test_probe_script.py`, change the namespace line to

```python
    await probe.probe_carriers(argparse.Namespace(file=str(codes), parse=True))
```

and append:

```python
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
```

- [ ] **Step 4: Run the tests and confirm they fail**

Run: `.\.venv\Scripts\python -m pytest tests/test_spx.py tests/test_probe_script.py -q`
Expected: collection error `ImportError: cannot import name 'SPX_ORDER_INFO_URL'` for `test_spx.py`; `test_probe_script.py` fails (`build_request()` takes 4 positional arguments / `spx_secret` attribute missing on the namespace).

- [ ] **Step 5: Implement** — replace `src/vn_parcel_bot/carriers/spx.py` with:

```python
from dataclasses import replace
from datetime import UTC, datetime

import httpx

from vn_parcel_bot.carrier_catalog import CarrierCode
from vn_parcel_bot.carriers.common import clean_text, json_body, request
from vn_parcel_bot.carriers.models import CarrierError, TrackingEvent, TrackingResult

SPX_ORDER_INFO_URL = "https://spx.vn/shipment/order/open/order/get_order_info"
NOT_FOUND_RETCODES = (2,)
PUBLIC_DISPLAY_FLAG = 1
DELIVERED_MILESTONE = 8
DELIVERED_TRACKING_CODES = ("F980",)
RETURNED_MARKERS = ("return", "hoàn hàng", "trả hàng")


def _parse_error(detail: str) -> CarrierError:
    return CarrierError("spx", "parse", detail)


def _location(record: dict, description: str) -> str | None:
    current = record.get("current_location")
    if not isinstance(current, dict):
        return None
    name = clean_text(current.get("location_name") or "")
    if not name or name.casefold() in description.casefold():
        return None
    return name


def _public_record(record: object) -> tuple[TrackingEvent, dict] | None:
    if not isinstance(record, dict):
        raise _parse_error("record is not an object")
    if record.get("display_flag") != PUBLIC_DISPLAY_FLAG:
        return None
    timestamp = record.get("actual_time")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise _parse_error("record without actual_time")
    description = clean_text(record.get("description") or "")
    if not description:
        raise _parse_error("record without description")
    code = record.get("tracking_code")
    event = TrackingEvent(
        time=datetime.fromtimestamp(timestamp, UTC),
        description=description,
        location=_location(record, description),
        raw_status=str(code) if code else None,
    )
    return event, record


def parse_spx_response(payload: object, tracking_number: str) -> TrackingResult:
    if not isinstance(payload, dict) or "retcode" not in payload:
        raise _parse_error("unexpected payload")
    not_found = TrackingResult(carrier="spx", tracking_number=tracking_number, found=False)
    retcode = payload["retcode"]
    if retcode in NOT_FOUND_RETCODES:
        return not_found
    if retcode != 0:
        raise _parse_error(f"retcode={retcode}")
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return not_found
    info = data.get("sls_tracking_info")
    if info is None:
        return not_found
    if not isinstance(info, dict):
        raise _parse_error("sls_tracking_info is not an object")
    records = info.get("records")
    if records is None or records == []:
        return not_found
    if not isinstance(records, list):
        raise _parse_error("records is not a list")

    kept = [pair for record in records if (pair := _public_record(record)) is not None]
    if not kept:
        return not_found

    result = TrackingResult(
        carrier="spx",
        tracking_number=tracking_number,
        found=True,
        events=tuple(event for event, _ in kept),
    )
    _, latest = max(kept, key=lambda pair: pair[0].time)
    delivered = (
        latest.get("milestone_code") == DELIVERED_MILESTONE
        or latest.get("tracking_code") in DELIVERED_TRACKING_CODES
    )
    status_texts = [
        clean_text(latest.get(field) or "").casefold()
        for field in ("description", "tracking_name", "milestone_name")
    ]
    returned = not delivered and any(
        marker in text for text in status_texts for marker in RETURNED_MARKERS
    )
    return replace(result, delivered=delivered, returned=returned)


class SpxCarrier:
    code: CarrierCode = "spx"
    display_name = "SPX"
    needs_phone = False

    async def fetch(
        self, http: httpx.AsyncClient, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        response = await request(
            http,
            "spx",
            "GET",
            SPX_ORDER_INFO_URL,
            params={"language_code": "vi", "spx_tn": tracking_number},
        )
        return parse_spx_response(json_body("spx", response), tracking_number)
```

In `scripts/probe_carriers.py`:

1. Delete the lines `import time` and `from vn_parcel_bot.carriers.spx import SpxCarrier`.
2. Replace the signature and SPX branch of `build_request` with:

```python
def build_request(
    carrier: str, code: str, last4: str | None
) -> tuple[str, str, dict[str, Any], str]:
    if carrier == "spx":
        params = {"language_code": "vi", "spx_tn": code}
        return (
            "GET",
            "https://spx.vn/shipment/order/open/order/get_order_info",
            {"params": params},
            "json",
        )
```

(the `jt`, `cainiao`, `fourpx`, `ninjavan`, `ghn` and BEST branches below stay unchanged).
3. In `event_count`, change the SPX path to `"spx": ("data", "sls_tracking_info", "records"),`.
4. Replace the start of `parse_summary` with:

```python
async def parse_summary(http: httpx.AsyncClient, carrier: str, code: str, last4: str | None) -> str:
    prefix = f"{carrier:9} {mask(code)} parse"
    if carrier not in CARRIERS:
        return f"{prefix} skipped: not a tracked carrier"
    fetcher = CARRIERS[carrier]
```

5. In `probe_carriers`, call `build_request(carrier, code, last4)` and `parse_summary(http, carrier, code, last4)`.
6. In `main`, delete the `carriers.add_argument("--spx-secret", …)` line.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `.\.venv\Scripts\python -m pytest tests/test_spx.py tests/test_probe_script.py tests/test_carrier_registry.py -q`
Expected: all pass.

Then: `.\.venv\Scripts\python -m ruff check . --fix; .\.venv\Scripts\python -m ruff format .; .\.venv\Scripts\python -m ruff check .; .\.venv\Scripts\python -m ruff format --check .; .\.venv\Scripts\python -m pytest -q`
Expected: `All checks passed!`, everything formatted, full suite green.

Leftover check: search for `spx_secret|sign_spx_code|SPX_SIGNING_SECRET|SPX_TRACKING_URL|fleet_order|sls_tracking_number` outside `docs/`, `BUILD_PLAN.md` and `SPEC.md`. Expected: no matches.

- [ ] **Step 7: Commit**

```powershell
git add tests/fixtures/spx/in_transit.json tests/fixtures/spx/delivered.json tests/fixtures/spx/not_found.json tests/fixtures/FIXTURES.md tests/test_spx.py tests/test_probe_script.py src/vn_parcel_bot/carriers/spx.py scripts/probe_carriers.py
git commit -m "fix: track SPX through the order-info endpoint spx.vn's page uses" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`nClaude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN"
```

---

### Task 2: Spec 1.3 (BUILD_PLAN.md Part 2 and SPEC.md)

**Files:**
- Modify: `BUILD_PLAN.md` (header, changes list, §5.1 SPX row, §5.3, §8 tree line, §9 SPX stubs, R1)
- Regenerate: `SPEC.md`

**Interfaces:**
- Consumes: Task 1's names (`SPX_ORDER_INFO_URL`, `NOT_FOUND_RETCODES`, `PUBLIC_DISPLAY_FLAG`, `DELIVERED_MILESTONE`, `DELIVERED_TRACKING_CODES`, `RETURNED_MARKERS`, `SpxCarrier` without constructor arguments).
- Produces: documentation only.

- [ ] **Step 1: Write the update script** `E:\Temp\claude\C--Users-hozkg\bfbff226-59df-4322-9e19-aa36ae7aa76c\scratchpad\update_spec_spx_13.py`:

```python
import re
from pathlib import Path

ROOT = Path(r"C:\Users\hozkg\projects\vn-parcel-bot")
path = ROOT / "BUILD_PLAN.md"
text = path.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global text
    assert text.count(old) == 1, (old[:80], text.count(old))
    text = text.replace(old, new)


def between(start: str, end: str, new_body: str) -> None:
    global text
    i = text.index(start) + len(start)
    j = text.index(end, i)
    text = text[:i] + new_body + text[j:]


sub(
    "Version 1.2 · 2026-09-14 · Status: v1 built on branch build/v1; live verification in progress",
    "Version 1.3 · 2026-09-14 · Status: v1 built on branch build/v1; live verification in progress",
)
sub(
    "## Changes in 1.2 (2026-09-14)\n",
    "## Changes in 1.3 (2026-09-14)\n\n"
    "- **SPX endpoint** (§5.1, §5.3, §9, R1): the bot reads `get_order_info`, the endpoint spx.vn's own "
    "tracking page loads the timeline from. The old `fleet_order/tracking/search` endpoint returned "
    "`data: {}` for a real code that spx.vn showed as out for delivery. A plain request works; signing, "
    "`SPX_SIGNING_SECRET` and `sign_spx_code` are removed. Part 3 prompts that mention SPX signing are "
    "historical; Part 2 wins.\n\n"
    "## Changes in 1.2 (2026-09-14)\n",
)
sub(
    "| `spx` | SPX | tracked | no | JSON API answers without captcha; real-data signing unverified (§5.3) | – |",
    "| `spx` | SPX | tracked | no | JSON endpoint used by spx.vn's tracking page; verified with a real code 2026-09-14 (§5.3) | – |",
)
between(
    "### 5.3 SPX Express Vietnam\n\n",
    "Tracking code format: `SPXVN`",
    "| Item | Value | Confidence |\n"
    "|---|---|---|\n"
    "| Endpoint | `GET https://spx.vn/shipment/order/open/order/get_order_info?language_code=vi&spx_tn=<CODE>`, the call spx.vn's tracking page makes | Verified with a real code (2026-09-14): plain request, no signature or page headers |\n"
    '| Unknown code | `{"retcode": 2, "message": "…find [0]:get logistic order index map error", "data": {}}` | Verified (2026-09-14) |\n'
    "| Found response | `retcode 0`; `data.sls_tracking_info.records[]`, newest first, with `actual_time` (int, Unix seconds), `description`, `tracking_code` (`F980` delivered, `F600` out for delivery), `milestone_code` (int; `8` delivered), `milestone_name`, `tracking_name`, `display_flag` (`1` = shown on spx.vn), `current_location.location_name` | Verified (2026-09-14) |\n"
    "| Personal data | The same response carries `receiver_name`, `driver_phone_number`, `client_order_id`, `buyer_description`, `epod`, addresses and coordinates | Never read, stored, logged or put in fixtures |\n"
    "| Old endpoint | `GET https://spx.vn/api/v2/fleet_order/tracking/search` returns `data: {}` for real codes | Not used |\n"
    "\n"
    "- Parsing: payload not an object or without `retcode` → `parse` error. `retcode` in `NOT_FOUND_RETCODES = (2,)` → not found; any other non-zero `retcode` → `parse` error. `data` missing/empty, `sls_tracking_info` missing, or `records` missing/empty → not found. `sls_tracking_info` not an object or `records` not a list → `parse` error.\n"
    "- Records with `display_flag != 1` are skipped. A kept record that is not an object, lacks an integer `actual_time` (bool rejected) or has an empty `description` after whitespace collapsing → `parse` error. No kept records → not found.\n"
    "- Event: `time = datetime.fromtimestamp(actual_time, UTC)`; `description` whitespace-collapsed; `location` = whitespace-collapsed `current_location.location_name` only when non-empty and not already contained in the description (case-insensitive), else `None`; `raw_status = tracking_code`.\n"
    '- `delivered` = the latest kept record has `milestone_code == 8` or `tracking_code == "F980"`. `returned` = not delivered and any of `return`, `hoàn hàng`, `trả hàng` (casefold substring) in that record\'s `description`, `tracking_name` or `milestone_name`.\n'
    "\n",
)
sub(
    "│  │  ├─ spx.py                 parse_spx_response, sign_spx_code, SpxCarrier",
    "│  │  ├─ spx.py                 parse_spx_response, SpxCarrier",
)
between(
    "# spx.py\n",
    "\n# jt.py\n",
    'SPX_ORDER_INFO_URL = "https://spx.vn/shipment/order/open/order/get_order_info"\n'
    "NOT_FOUND_RETCODES = (2,)\n"
    "PUBLIC_DISPLAY_FLAG = 1\n"
    "DELIVERED_MILESTONE = 8\n"
    'DELIVERED_TRACKING_CODES = ("F980",)\n'
    'RETURNED_MARKERS = ("return", "hoàn hàng", "trả hàng")\n'
    "def parse_spx_response(payload: object, tracking_number: str) -> TrackingResult: ...\n"
    'class SpxCarrier:  code = "spx"; display_name = "SPX"; needs_phone = False\n'
    '    # fetch: GET SPX_ORDER_INFO_URL with params {"language_code": "vi", "spx_tn": code}\n',
)
r1 = re.search(r"^\| R1 \|.*$", text, re.M)
assert r1 and "signed request" in r1.group(0)
text = (
    text[: r1.start()]
    + "| R1 | SPX changes or blocks the order-info endpoint its tracking page uses | Medium | High | "
    "Resolved 2026-09-14: the page's own endpoint answers plain requests (§5.3); blocks surface as `blocked` "
    "with backoff and admin alerts, replies keep the spx.vn link; no evasion |" + text[r1.end() :]
)

part2_end = text.index("\n# Part 3 — Prompts\n")
assert (
    "sign_spx_code"
    not in text[:part2_end].split("## Changes in 1.3", 1)[1].split("# Part 2 — Specification", 1)[1]
)
assert text.count("```") % 2 == 0, "unbalanced code fences"
path.write_text(text, encoding="utf-8")

part2 = text[text.index("# Part 2 — Specification\n") : part2_end]
part2 = part2.rstrip().removesuffix("---").rstrip() + "\n"
spec = (
    "<!-- Generated from BUILD_PLAN.md Part 2 (version 1.3). Do not edit by hand: "
    "edit BUILD_PLAN.md and regenerate. -->\n\n"
    + part2.replace("# Part 2 — Specification", "# vn-parcel-bot — Specification", 1)
)
(ROOT / "SPEC.md").write_text(spec, encoding="utf-8")
print("BUILD_PLAN.md 1.3 and SPEC.md updated")
```

- [ ] **Step 2: Run it**

Run: `.\.venv\Scripts\python "E:\Temp\claude\C--Users-hozkg\bfbff226-59df-4322-9e19-aa36ae7aa76c\scratchpad\update_spec_spx_13.py"`
Expected: `BUILD_PLAN.md 1.3 and SPEC.md updated`.

- [ ] **Step 3: Verify**

Search `SPEC.md` for `sign_spx_code|SPX_SIGNING_SECRET|fleet_order/tracking/search\?sls|Request signing`. Expected: only the "Old endpoint … Not used" row mentions `fleet_order/tracking/search`. `git diff --stat` shows only `BUILD_PLAN.md` and `SPEC.md` for this task.

- [ ] **Step 4: Commit**

```powershell
git add BUILD_PLAN.md SPEC.md
git commit -m "docs: spec 1.3, SPX order-info endpoint" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`nClaude-Session: https://claude.ai/code/session_01JNknSSDZMR9Cg8iyhqGxQN"
```

---

### Task 3: Restart and live check

**Files:** none committed. Uses `probe_codes.local.txt` (git-ignored) and `data/bot.sqlite3`.

**Interfaces:**
- Consumes: Task 1's `SpxCarrier` via `CARRIERS`, probe `--parse`.
- Produces: a verified running bot.

- [ ] **Step 1: Probe the real SPX code**

Write `probe_codes.local.txt` with one line `spx <the SPX code stored in data/bot.sqlite3>` (read it from the `parcels` table; never print it in full).
Run: `.\.venv\Scripts\python scripts\probe_carriers.py carriers --parse`
Expected: `spx       SPXVN…319 HTTP 200 … keys=['data', 'debug', 'detail', 'message', 'retcode'] events=17` and `spx       SPXVN…319 parse found=True events=8 delivered=True returned=False`.

- [ ] **Step 2: Restart the bot safely**

```powershell
Stop-ScheduledTask -TaskName "VN Parcel Bot"
$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'vn_parcel_bot' })
foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
if ($procs.Count -gt 0) { try { Wait-Process -Id $procs.ProcessId -Timeout 20 -ErrorAction Stop } catch {} }
Start-ScheduledTask -TaskName "VN Parcel Bot"
```

Expected: `logs/bot.log` gains `bot started as @vn_parcel_hozk_bot` with no `another instance is running` line after it.

- [ ] **Step 3: Confirm the first poll picks up the SPX parcel**

About 30 s after start (`FIRST_POLL_DELAY_SECONDS`), check `logs/bot.log` for a `poll cycle` line with `new_events` ≥ 8 and no SPX `carrier error`, and the SPX row in `parcels` with `state = 'delivered'` and a `last_status_text` of `Giao hàng thành công`. The user receives the delivered notification in Telegram.
