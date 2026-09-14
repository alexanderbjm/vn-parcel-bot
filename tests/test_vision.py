import json
from dataclasses import replace

import httpx
import pytest
import respx

from vn_parcel_bot.config import Settings
from vn_parcel_bot.services.vision import ANTHROPIC_API_URL, VisionService


@pytest.fixture
def vision_settings(settings: Settings) -> Settings:
    return replace(
        settings,
        anthropic_api_key="sk-ant-test-key-12345",
        anthropic_model="claude-3-5-haiku-20241022",
    )


def test_vision_service_is_configured(settings: Settings, vision_settings: Settings):
    unconfigured = VisionService(settings)
    assert not unconfigured.is_configured

    configured = VisionService(vision_settings)
    assert configured.is_configured


async def test_analyze_unconfigured_returns_error(settings: Settings):
    service = VisionService(settings)
    result = await service.analyze_image(b"fake-bytes")
    assert result.error == "Vision service is not configured"


@respx.mock
async def test_analyze_image_success_json(vision_settings: Settings):
    respx.post(ANTHROPIC_API_URL).respond(
        status_code=200,
        json={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "tracking_codes": ["SPXVN01234567890"],
                            "order_ids": ["240914ABCDEF12"],
                            "carrier": "SPX Express",
                            "phone_last4": "0987654321",
                            "notes": "Shopee waybill label",
                        }
                    ),
                }
            ]
        },
    )

    async with httpx.AsyncClient() as http:
        service = VisionService(vision_settings, http)
        result = await service.analyze_image(b"fake-bytes", media_type="image/jpeg")

    assert result.error is None
    assert result.tracking_codes == ("SPXVN01234567890",)
    assert result.order_ids == ("240914ABCDEF12",)
    assert result.carrier == "SPX Express"
    assert result.phone_last4 == "4321"
    assert result.notes == "Shopee waybill label"


@respx.mock
async def test_analyze_image_markdown_fence_json(vision_settings: Settings):
    respx.post(ANTHROPIC_API_URL).respond(
        status_code=200,
        json={
            "content": [
                {
                    "type": "text",
                    "text": "```json\n"
                    + json.dumps(
                        {
                            "tracking_code": "840000000001",
                            "carrier": "J&T",
                            "phone_last4": "1234",
                        }
                    )
                    + "\n```",
                }
            ]
        },
    )

    async with httpx.AsyncClient() as http:
        service = VisionService(vision_settings, http)
        result = await service.analyze_image(b"fake-bytes")

    assert result.error is None
    assert result.tracking_codes == ("840000000001",)
    assert result.carrier == "J&T"
    assert result.phone_last4 == "1234"


@respx.mock
async def test_analyze_image_fallback_to_text_codes(vision_settings: Settings):
    respx.post(ANTHROPIC_API_URL).respond(
        status_code=200,
        json={
            "content": [
                {
                    "type": "text",
                    "text": "I see the tracking code SPXVN0987654321 on the receipt.",
                }
            ]
        },
    )

    async with httpx.AsyncClient() as http:
        service = VisionService(vision_settings, http)
        result = await service.analyze_image(b"fake-bytes")

    assert result.error is None
    assert result.tracking_codes == ("SPXVN0987654321",)


@respx.mock
async def test_analyze_image_order_number_only(vision_settings: Settings):
    respx.post(ANTHROPIC_API_URL).respond(
        status_code=200,
        json={
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "tracking_codes": [],
                            "order_ids": ["500000000000001"],
                            "notes": "Shopee order screen without tracking code yet",
                        }
                    ),
                }
            ]
        },
    )

    async with httpx.AsyncClient() as http:
        service = VisionService(vision_settings, http)
        result = await service.analyze_image(b"fake-bytes")

    assert result.error is None
    assert result.tracking_codes == ()
    assert result.order_ids == ("500000000000001",)


@respx.mock
async def test_analyze_image_api_error(vision_settings: Settings):
    respx.post(ANTHROPIC_API_URL).respond(
        status_code=401,
        json={"error": {"type": "authentication_error", "message": "invalid api key"}},
    )

    async with httpx.AsyncClient() as http:
        service = VisionService(vision_settings, http)
        result = await service.analyze_image(b"fake-bytes")

    assert result.error == "HTTP 401"
