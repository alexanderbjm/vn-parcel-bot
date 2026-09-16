import logging
import time

import httpx

from vn_parcel_bot.agy_proxy import PROXY_HEADER, READ_PATH, REREAD_HEADER
from vn_parcel_bot.config import Settings
from vn_parcel_bot.services.vision import (
    SUPPORTED_MEDIA_TYPES,
    VisionResult,
    doubtful_codes,
    parse_vision_text,
)

log = logging.getLogger(__name__)

PROXY_ERRORS = frozenset({"not_configured", "timeout", "cli_error", "invalid_response", "blocked"})


def proxy_wait_seconds(settings: Settings) -> float:
    """Room for the proxy's first model, its fallback model and some slack."""
    return settings.vision_timeout_seconds * 2 + 60


class AgyProxyVisionEngine:
    """Sends screenshots to the local agy proxy (``python -m vn_parcel_bot.agy_proxy``).

    When a code is unknown to every carrier or has a length its carrier never uses, the image is
    read once more with a note asking agy to count the characters again.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.agy_proxy_url)

    async def analyze_image(
        self, image_bytes: bytes, media_type: str = "image/jpeg"
    ) -> VisionResult:
        if media_type not in SUPPORTED_MEDIA_TYPES:
            media_type = "image/jpeg"
        first = await self._read(image_bytes, media_type, reread=False)
        doubtful = doubtful_codes(first)
        if first.error is not None or doubtful == 0:
            return first
        log.info("vision agy reread doubtful_codes=%d", doubtful)
        second = await self._read(image_bytes, media_type, reread=True)
        if (
            second.error is None
            and len(second.tracking_codes) >= len(first.tracking_codes)
            and doubtful_codes(second) <= doubtful
        ):
            log.info("vision agy reread used doubtful_codes=%d", doubtful_codes(second))
            return second
        log.info("vision agy reread kept the first read")
        return first

    async def _read(self, image_bytes: bytes, media_type: str, *, reread: bool) -> VisionResult:
        url = self._settings.agy_proxy_url.rstrip("/") + READ_PATH
        headers = {"Content-Type": media_type, PROXY_HEADER: "1"}
        if reread:
            headers[REREAD_HEADER] = "1"
        started = time.monotonic()
        try:
            # trust_env=False: never route this PC-local call through HTTP(S)_PROXY.
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.post(
                    url,
                    content=image_bytes,
                    headers=headers,
                    timeout=proxy_wait_seconds(self._settings),
                )
        except httpx.TimeoutException:
            log.warning("vision agy error=timeout duration=%.1fs", time.monotonic() - started)
            return VisionResult(error="timeout")
        except httpx.HTTPError as exc:
            log.warning(
                "vision agy error=network type=%s (is the OCR proxy running?)", type(exc).__name__
            )
            return VisionResult(error="network")
        elapsed = time.monotonic() - started
        if response.status_code != 200:
            log.warning("vision agy error=http_status status=%s", response.status_code)
            return VisionResult(error="http_status")
        try:
            data = response.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            log.warning("vision agy error=invalid_response duration=%.1fs", elapsed)
            return VisionResult(error="invalid_response")
        error = data.get("error")
        if error is not None:
            code = error if error in PROXY_ERRORS else "cli_error"
            log.warning("vision agy error=%s duration=%.1fs", code, elapsed)
            return VisionResult(error=code)
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            log.warning("vision agy error=invalid_response duration=%.1fs", elapsed)
            return VisionResult(error="invalid_response")
        log.info("vision agy ok duration=%.1fs", elapsed)
        return parse_vision_text(text)
