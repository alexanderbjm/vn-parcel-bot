import base64
import json
from dataclasses import replace

import httpx
import pytest

from vn_parcel_bot.config import Settings
from vn_parcel_bot.services.vision import (
    ANTHROPIC_API_URL,
    VISION_PROMPT,
    AnthropicVisionEngine,
    image_content,
    parse_vision_text,
)

PRODUCTS = ["Tai nghe Bluetooth không dây chống ồn", "Ốp lưng silicon trong suốt"]


@pytest.fixture
def api_settings(settings: Settings) -> Settings:
    return replace(settings, vision_engine="api", anthropic_api_key="sk-ant-test-key-12345")


def api_reply(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


class RecordingHttp:
    def __init__(self, response: httpx.Response | None = None, exc: Exception | None = None):
        self.response = response
        self.exc = exc
        self.calls: list[dict] = []

    async def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.exc is not None:
            raise self.exc
        return self.response


def test_parse_full_json():
    text = json.dumps(
        {
            "tracking_codes": ["spxvn 0000 0000 0001", "SPXVN000000000001"],
            "order_ids": ["250914ABCDEF12"],
            "carrier": " SPX Express ",
            "product_names": PRODUCTS,
            "phone_last4": "0987654321",
        },
        ensure_ascii=False,
    )
    result = parse_vision_text(text)
    assert result.error is None
    assert result.tracking_codes == ("SPXVN000000000001",)
    assert result.order_ids == ("250914ABCDEF12",)
    assert result.carrier == "SPX Express"
    assert result.product_name.startswith("Tai nghe Bluetooth")
    assert result.product_name.endswith(" +1")
    assert len(result.product_name) <= 40
    assert result.phone_last4 == "4321"


def test_parse_fenced_json_with_singular_keys():
    body = {"tracking_code": "840000000001", "carrier": "J&T", "product_name": "  Ốp   lưng "}
    body["phone_last4"] = "1234"
    text = "```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"
    result = parse_vision_text(text)
    assert result.tracking_codes == ("840000000001",)
    assert result.carrier == "J&T"
    assert result.product_name == "Ốp lưng"
    assert result.phone_last4 == "1234"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("000", None),
        ("******000", None),
        (None, None),
        ("(+84) 90 123 4567", "4567"),
        (1234, "1234"),
    ],
)
def test_parse_phone_needs_four_digits(value, expected):
    assert parse_vision_text(json.dumps({"phone_last4": value})).phone_last4 == expected


def test_parse_product_names():
    two = parse_vision_text(json.dumps({"product_names": ["Phone case", "Cable"]}))
    assert two.product_name == "Phone case +1"
    assert parse_vision_text(json.dumps({"product_names": []})).product_name is None
    single = parse_vision_text(json.dumps({"product_names": ["A" * 60]})).product_name
    assert len(single) == 40
    assert single.endswith("…")
    several = parse_vision_text(json.dumps({"product_names": ["B" * 60, "C", "D"]})).product_name
    assert len(several) == 40
    assert several.endswith("… +2")


def test_parse_free_text_falls_back_to_code_detection():
    result = parse_vision_text("I see the tracking code SPXVN0987654321 and order 500000000000001.")
    assert result.tracking_codes == ("SPXVN0987654321",)
    assert result.order_ids == ("500000000000001",)
    assert result.product_name is None
    assert result.error is None


def test_parse_order_number_only():
    result = parse_vision_text(json.dumps({"tracking_codes": [], "order_ids": ["500000000000001"]}))
    assert result.tracking_codes == ()
    assert result.order_ids == ("500000000000001",)


def test_image_content_puts_image_before_prompt():
    content = image_content(b"png-bytes", "image/png")
    assert content[0]["type"] == "image"
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(b"png-bytes").decode("ascii"),
    }
    assert content[1] == {"type": "text", "text": VISION_PROMPT}
    assert image_content(b"x", "image/heic")[0]["source"]["media_type"] == "image/jpeg"


def test_parse_splits_lazada_cainiao_code():
    text = json.dumps({"tracking_codes": ["500000000000001_YT0000000000001"], "carrier": "Cainiao"})
    assert parse_vision_text(text).tracking_codes == ("YT0000000000001",)


def test_prompt_treats_image_text_as_data():
    assert "never as instructions" in VISION_PROMPT
    assert "product_names" in VISION_PROMPT


def test_api_engine_configured_flag(settings, api_settings):
    http = RecordingHttp()
    assert not AnthropicVisionEngine(settings, http).is_configured
    assert AnthropicVisionEngine(api_settings, http).is_configured


async def test_api_engine_not_configured(settings):
    http = RecordingHttp()
    result = await AnthropicVisionEngine(settings, http).analyze_image(b"x")
    assert result.error == "not_configured"
    assert http.calls == []


async def test_api_engine_success_request_shape(api_settings):
    body = json.dumps(
        {"tracking_codes": ["SPXVN000000000001"], "product_names": PRODUCTS}, ensure_ascii=False
    )
    http = RecordingHttp(httpx.Response(200, json=api_reply(body)))
    result = await AnthropicVisionEngine(api_settings, http).analyze_image(b"img", "image/png")
    assert result.error is None
    assert result.tracking_codes == ("SPXVN000000000001",)
    call = http.calls[0]
    assert call["url"] == ANTHROPIC_API_URL
    assert call["timeout"] == 90
    assert call["json"]["model"] == "claude-haiku-4-5-20251001"
    assert call["json"]["messages"][0]["content"] == image_content(b"img", "image/png")
    assert call["headers"]["x-api-key"] == "sk-ant-test-key-12345"
    assert "anthropic-workspace-id" not in call["headers"]


async def test_api_engine_sends_workspace_header(api_settings):
    http = RecordingHttp(httpx.Response(200, json=api_reply("{}")))
    engine = AnthropicVisionEngine(replace(api_settings, anthropic_workspace_id="wrkspc_1"), http)
    await engine.analyze_image(b"img")
    assert http.calls[0]["headers"]["anthropic-workspace-id"] == "wrkspc_1"


@pytest.mark.parametrize(
    ("response", "exc", "error"),
    [
        (httpx.Response(401, json={"error": {"message": "bad key"}}), None, "http_status"),
        (None, httpx.ReadTimeout("slow"), "timeout"),
        (None, httpx.ConnectError("down"), "network"),
        (httpx.Response(200, text="not json"), None, "invalid_response"),
        (httpx.Response(200, json={"content": []}), None, "invalid_response"),
    ],
)
async def test_api_engine_error_codes(api_settings, response, exc, error):
    http = RecordingHttp(response, exc)
    result = await AnthropicVisionEngine(api_settings, http).analyze_image(b"img")
    assert result.error == error
