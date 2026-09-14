# Carrier fixtures

Facts that the parser tests assert. Provenance is either `synthetic` (hand-built from the shapes in `BUILD_PLAN.md` §5) or `live YYYY-MM-DD` (sanitized capture, Prompt 10A). Only fake codes appear here and in the fixture files. "Oldest local" is the oldest event's time in Asia/Ho_Chi_Minh as `dd/mm HH:MM`. All files list events newest first, as the carriers are believed to serve them.

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

## J&T Express Vietnam

- Provenance: **synthetic 2026-09-13** (real markup unknown until Prompt 10A)
- Request: `GET https://jtexpress.vn/tracking?type=track&billcode=<code>&cellphone=<last4>`
- Selectors: result `.result-tracking`; bill block `[data-billcode]`; event `.tracking-event`; time `.event-time`; description `.event-desc`; location `.event-location` (optional)
- Time format: `dd/mm/yyyy HH:MM` local (Asia/Ho_Chi_Minh)
- Not found: text `Không tìm thấy dữ liệu về vận đơn` and `<div class="empty-vandon"></div>`
- Delivered marker: `Giao hàng thành công`; returned marker: none in these files
- `jt/in_transit.html`: the oldest event (`Đã lấy hàng thành công`) has no location

| File | Code | Events | Latest description | Oldest local |
|---|---|---|---|---|
| `jt/in_transit.html` | `840000000001` | 4 | Đơn hàng đang được giao đến bạn | 10/09 09:30 |
| `jt/delivered.html` | `840000000002` | 3 | Giao hàng thành công | 10/09 11:45 |
| `jt/not_found.html` | – | 0 | – | – |

## Cainiao

- Provenance: **synthetic 2026-09-13**
- Request: `GET https://global.cainiao.com/global/detail.json?mailNos=<code>&lang=en-US&language=en-US`
- Paths: `success`; `module[0].detailList[]` → `time` (epoch ms), `timeStr` (`yyyy-MM-dd HH:mm:ss`), `timeZone` (`GMT+8`), `desc`, `standerdDesc`, `actionCode`
- Not found: `module[0].mailNoSource == "EXTERNAL"` with empty `detailList` (verified 2026-09-13)
- Delivered marker: latest `actionCode` `GTMS_SIGNED`
- `cainiao/in_transit.json`: the item `Đã thông quan nhập khẩu` has no `time`; from `timeStr` 2026-09-10 20:00:00 GMT+8 it is **2026-09-10 12:00 UTC**

| File | Code | Events | Latest description | Oldest local |
|---|---|---|---|---|
| `cainiao/in_transit.json` | `LP00000000000001` | 4 | Đã đến trung tâm phân loại tại Việt Nam | 08/09 21:10 |
| `cainiao/delivered.json` | `LP00000000000002` | 3 | Giao hàng thành công | 11/09 08:00 |
| `cainiao/not_found.json` | `LP00000000000000` | 0 | – | – |

## 4PX

- Provenance: **synthetic 2026-09-13** (descriptions in English, matching `language=en-us`)
- Request: `POST https://track.4px.com/track/v2/front/listTrackV3` with JSON `{"queryCodes": ["<code>"], "language": "en-us", "translateLanguage": "en-us"}`
- Paths: `result`; `data[0].tracks[]` → `tkCode`, `tkDesc`, `tkLocation`, `tkTimezone`, `tkDateStr`, `tkTranslatedDesc`
- Not found: `data[0].tracks` null, `status` 7 (verified 2026-09-13)
- Delivered marker: latest `tkCode` starting with `FPX_S_OK`
- `fourpx/in_transit.json` UTC times: `Shipment arrived at facility` (+08:00) **2026-09-09 13:15 UTC**; `Departed from airport` (+08:00) **2026-09-10 10:30 UTC**; `Arrived at destination country delivery center` (GMT+7) **2026-09-11 03:00 UTC**

| File | Code | Events | Latest description | Oldest local |
|---|---|---|---|---|
| `fourpx/in_transit.json` | `4PX0000000000000001` | 3 | Arrived at destination country delivery center | 09/09 20:15 |
| `fourpx/delivered.json` | `4PX0000000000000002` | 3 | Delivered | 11/09 10:00 |
| `fourpx/not_found.json` | `4PX0000000000000000` | 0 | – | – |

## Ninja Van Vietnam

- Provenance: **synthetic 2026-09-13**
- Request: `GET https://api.ninjavan.co/vn/dash/1.2/public/orders?tracking_id=<code>`
- Paths: `events[]` → `type`, `time` (ISO-8601 or epoch ms), `data.hub_name`/`hubName`, `data.failure_reason`/`failureReason` (`vi`, `en`); `granular_status`/`granularStatus`
- `ninjavan/in_transit.json` uses snake_case and ISO times; `delivered.json` and `returned.json` use camelCase; `delivered.json` uses epoch-ms times
- Not found: HTTP 404 with `error.code` 150002 (verified 2026-09-13)
- Delivered: latest `type` `DELIVERY_SUCCESS`; returned: granular status `Returned to Sender`
- `ninjavan/in_transit.json`: latest description `Giao hàng thất bại – Không liên lạc được với khách hàng`; the `ARRIVED_AT_DESTINATION_HUB` event has location `Kho Hồ Chí Minh`
- `ninjavan/returned.json`: latest description `Giao hàng thành công`, returned, not delivered

| File | Code | Events | Latest description | Oldest local |
|---|---|---|---|---|
| `ninjavan/in_transit.json` | `SPEVN000000000001` | 4 | Giao hàng thất bại – Không liên lạc được với khách hàng | 10/09 09:30 |
| `ninjavan/delivered.json` | `SPEVN000000000002` | 3 | Giao hàng thành công | 11/09 20:00 |
| `ninjavan/returned.json` | `SPEVN000000000003` | 3 | Giao hàng thành công | 12/09 15:00 |
| `ninjavan/not_found.json` | – | 0 | – | – |

## GHN

- Provenance: **synthetic 2026-09-13**
- Request: `POST https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs` with JSON `{"order_code": "<code>", "phone_verify": sha256("<code>|<last4>")}`
- Paths: `code`; `data.order_info.status`; `data.tracking_logs[]` → `status`, `status_name`, `action_at` (ISO-8601 with `Z`), `location.address`
- Not found: HTTP 400 body `code` 400 (`PHONE_VERIFY_FAIL` for wrong digits)
- Delivered: `order_info.status` `delivered`
- `ghn/in_transit.json`: the `sorting` log has no `status_name` (text from `GHN_STATUS_TEXT`: `Đang phân loại hàng`) and no `location.address`

| File | Code | Events | Latest description | Oldest local |
|---|---|---|---|---|
| `ghn/in_transit.json` | `GA0000000001` | 3 | Đang giao hàng | 10/09 10:15 |
| `ghn/delivered.json` | `GA0000000002` | 3 | Giao hàng thành công | 11/09 19:00 |
| `ghn/not_found.json` | – | 0 | – | – |
