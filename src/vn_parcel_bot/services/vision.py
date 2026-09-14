import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from vn_parcel_bot.config import Settings
from vn_parcel_bot.tracking_codes import (
    extract_codes,
    is_order_number,
    is_valid_last4,
    normalize_code,
)

log = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

_PROMPT = (
    "You are an expert OCR and parcel extraction assistant for Vietnamese e-commerce orders "
    "(Shopee, Lazada, TikTok Shop, Tiki, Sendo) and domestic couriers (SPX Express, J&T Express, "
    "Ninja Van, GHN, GHTK, Viettel Post, VNPost, 4PX, Cainiao, BEST Express, etc.).\n\n"
    "Analyze the provided image (shipping waybill, parcel package label, "
    "order detail screenshot, or receipt). Extract:\n"
    "1. Tracking code (Mã vận đơn) — the tracking or waybill number used by the carrier, "
    "e.g., SPXVN..., VN..., JNT..., 84..., LP..., etc.\n"
    "2. Order ID (Mã đơn hàng) — the marketplace purchase order ID (e.g., 15 digits on Shopee).\n"
    "3. Carrier name (Đơn vị vận chuyển) — name of the delivery carrier if visible.\n"
    "4. Recipient phone number or last 4 digits (SĐT người nhận) — "
    "extract last 4 digits if present.\n"
    "5. Brief notes/description (e.g. 'Shopee screenshot showing SPX tracking number').\n\n"
    "Return JSON ONLY matching this format:\n"
    "{\n"
    '  "tracking_codes": ["string"],\n'
    '  "order_ids": ["string"],\n'
    '  "carrier": "string or null",\n'
    '  "phone_last4": "string or null",\n'
    '  "notes": "string or null"\n'
    "}"
)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class VisionResult:
    tracking_codes: tuple[str, ...] = ()
    order_ids: tuple[str, ...] = ()
    carrier: str | None = None
    phone_last4: str | None = None
    notes: str | None = None
    error: str | None = None


class VisionService:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.anthropic_api_key)

    async def analyze_image(
        self, image_bytes: bytes, media_type: str = "image/jpeg"
    ) -> VisionResult:
        if not self.is_configured:
            return VisionResult(error="Vision service is not configured")

        if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            media_type = "image/jpeg"

        b64_data = base64.b64encode(image_bytes).decode("ascii")

        payload = {
            "model": self._settings.anthropic_model,
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": _PROMPT,
                        },
                    ],
                }
            ],
        }

        headers = {
            "x-api-key": self._settings.anthropic_api_key or "",
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            client = self._http or httpx.AsyncClient(timeout=self._settings.http_timeout_seconds)
            response = await client.post(
                ANTHROPIC_API_URL,
                json=payload,
                headers=headers,
                timeout=self._settings.http_timeout_seconds,
            )
            if response.status_code != 200:
                log.warning(
                    "Anthropic API returned %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return VisionResult(error=f"HTTP {response.status_code}")

            data = response.json()
            return self._parse_response(data)
        except httpx.TimeoutException:
            log.warning("Anthropic API request timed out")
            return VisionResult(error="Request timed out")
        except Exception as exc:
            log.exception("Anthropic API call failed: %s", exc)
            return VisionResult(error=str(exc))

    def _parse_response(self, data: dict[str, Any]) -> VisionResult:
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        parsed = self._extract_json(text)
        if parsed is not None:
            raw_tracking = parsed.get("tracking_codes") or parsed.get("tracking_code")
            tracking_list: list[str] = []
            if isinstance(raw_tracking, str) and raw_tracking.strip():
                tracking_list.append(normalize_code(raw_tracking))
            elif isinstance(raw_tracking, list):
                for item in raw_tracking:
                    if isinstance(item, str) and item.strip():
                        norm = normalize_code(item)
                        if norm not in tracking_list:
                            tracking_list.append(norm)

            raw_orders = parsed.get("order_ids") or parsed.get("order_id")
            order_list: list[str] = []
            if isinstance(raw_orders, str) and raw_orders.strip():
                order_list.append(normalize_code(raw_orders))
            elif isinstance(raw_orders, list):
                for item in raw_orders:
                    if isinstance(item, str) and item.strip():
                        norm = normalize_code(item)
                        if norm not in order_list:
                            order_list.append(norm)

            carrier = parsed.get("carrier")
            if carrier is not None:
                carrier = str(carrier).strip() or None

            phone_last4 = parsed.get("phone_last4")
            if phone_last4 is not None:
                phone_str = re.sub(r"\D", "", str(phone_last4))
                if len(phone_str) >= 4:
                    phone_last4 = phone_str[-4:]
                elif is_valid_last4(str(phone_last4).strip()):
                    phone_last4 = str(phone_last4).strip()
                else:
                    phone_last4 = None

            notes = parsed.get("notes")
            if notes is not None:
                notes = str(notes).strip() or None

            if not tracking_list and not order_list:
                fallback_codes = extract_codes(text)
                for code in fallback_codes:
                    if is_order_number(code):
                        order_list.append(code)
                    else:
                        tracking_list.append(code)

            return VisionResult(
                tracking_codes=tuple(tracking_list),
                order_ids=tuple(order_list),
                carrier=carrier,
                phone_last4=phone_last4,
                notes=notes,
            )

        extracted = extract_codes(text)
        tracking_list = [c for c in extracted if not is_order_number(c)]
        order_list = [c for c in extracted if is_order_number(c)]
        return VisionResult(
            tracking_codes=tuple(tracking_list),
            order_ids=tuple(order_list),
            notes=text[:200] if text else None,
        )

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        trimmed = text.strip()
        try:
            val = json.loads(trimmed)
            if isinstance(val, dict):
                return val
        except (ValueError, json.JSONDecodeError):
            pass

        match = _JSON_BLOCK_RE.search(trimmed)
        if match:
            try:
                val = json.loads(match.group(1))
                if isinstance(val, dict):
                    return val
            except (ValueError, json.JSONDecodeError):
                pass

        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start != -1 and end > start:
            try:
                val = json.loads(trimmed[start : end + 1])
                if isinstance(val, dict):
                    return val
            except (ValueError, json.JSONDecodeError):
                pass

        return None
