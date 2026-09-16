import httpx

from vn_parcel_bot.config import Settings
from vn_parcel_bot.services.vision import AnthropicVisionEngine, VisionEngine
from vn_parcel_bot.services.vision_agy import AgyProxyVisionEngine
from vn_parcel_bot.services.vision_claude_code import ClaudeCodeVisionEngine
from vn_parcel_bot.services.vision_cmdc import CmdcVisionEngine


def build_vision_engine(settings: Settings, http: httpx.AsyncClient) -> VisionEngine:
    if settings.vision_engine == "api":
        return AnthropicVisionEngine(settings, http)
    if settings.vision_engine == "agy":
        return AgyProxyVisionEngine(settings)
    if settings.vision_engine == "cmdc":
        return CmdcVisionEngine(settings)
    return ClaudeCodeVisionEngine(settings)
