from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from tests.fakes import FakeCarrier
from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.bot.handlers_user import photo_message
from vn_parcel_bot.config import Settings
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller
from vn_parcel_bot.services.vision import VisionResult

T0 = datetime(2026, 9, 1, tzinfo=UTC)


class FakeFile:
    def __init__(self, data: bytes):
        self.data = data

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self.data)


class FakeBot:
    def __init__(self, data: bytes = b"fake-image-bytes"):
        self.data = data

    async def get_file(self, file_id: str) -> FakeFile:
        return FakeFile(self.data)


class FakeNotifier:
    async def send(self, *args, **kwargs):
        pass


class FakeVisionService:
    def __init__(self, is_configured: bool = True, result: VisionResult | None = None):
        self._is_configured = is_configured
        self._result = result or VisionResult()
        self.analyzed = []

    @property
    def is_configured(self) -> bool:
        return self._is_configured

    async def analyze_image(
        self, image_bytes: bytes, media_type: str = "image/jpeg"
    ) -> VisionResult:
        self.analyzed.append((image_bytes, media_type))
        return self._result


class FakeChat:
    async def send_action(self, action):
        pass


class MessageRecorder:
    def __init__(self, photo=None, document=None, caption=None):
        self.photo = photo
        self.document = document
        self.caption = caption
        self.texts: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)


@pytest.fixture
async def deps(settings: Settings) -> Deps:
    repo = await Repository.open(":memory:")
    await repo.upsert_user(111, now=T0, is_allowed=True, is_admin=True)
    spx = FakeCarrier("spx")
    jt = FakeCarrier("jt", needs_phone=True)
    http = httpx.AsyncClient()
    parcels = ParcelService(repo, {"spx": spx, "jt": jt}, http, settings, lambda: T0)
    poller = Poller(repo, {"spx": spx, "jt": jt}, http, FakeNotifier(), settings, lambda: T0)
    vision = FakeVisionService(is_configured=True)
    return Deps(settings, repo, http, parcels, poller, FakeNotifier(), vision=vision)


def make_update(message: MessageRecorder, user_id: int = 111):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, full_name="User"),
        effective_message=message,
        effective_chat=FakeChat(),
    )


def make_context(deps: Deps):
    return SimpleNamespace(
        bot_data={"deps": deps, "settings": deps.settings},
        user_data={},
        bot=FakeBot(),
    )


async def test_photo_not_configured(deps: Deps):
    deps.vision = FakeVisionService(is_configured=False)
    msg = MessageRecorder(photo=[SimpleNamespace(file_id="p1")])
    update = make_update(msg)
    context = make_context(deps)

    await photo_message(update, context)
    assert msg.texts == [texts.VISION_NOT_CONFIGURED]


async def test_photo_vision_error(deps: Deps):
    deps.vision = FakeVisionService(result=VisionResult(error="API failure"))
    msg = MessageRecorder(photo=[SimpleNamespace(file_id="p1")])
    update = make_update(msg)
    context = make_context(deps)

    await photo_message(update, context)
    assert any("API failure" in t for t in msg.texts)


async def test_photo_no_data(deps: Deps):
    deps.vision = FakeVisionService(result=VisionResult())
    msg = MessageRecorder(photo=[SimpleNamespace(file_id="p1")])
    update = make_update(msg)
    context = make_context(deps)

    await photo_message(update, context)
    assert msg.texts == [texts.VISION_NO_DATA]


async def test_photo_tracking_code_found(deps: Deps):
    deps.vision = FakeVisionService(
        result=VisionResult(
            tracking_codes=("SPXVN000000000001",),
            carrier="SPX",
        )
    )
    msg = MessageRecorder(photo=[SimpleNamespace(file_id="p1")])
    update = make_update(msg)
    context = make_context(deps)

    await photo_message(update, context)
    assert len(msg.texts) == 1
    reply_text = msg.texts[0]
    assert "SPXVN000000000001" in reply_text
    assert "SPX" in reply_text
    assert "Nhận diện từ hình ảnh" in reply_text


async def test_photo_order_id_only(deps: Deps):
    deps.vision = FakeVisionService(result=VisionResult(order_ids=("500000000000001",)))
    msg = MessageRecorder(photo=[SimpleNamespace(file_id="p1")])
    update = make_update(msg)
    context = make_context(deps)

    await photo_message(update, context)
    assert len(msg.texts) == 1
    assert "500000000000001" in msg.texts[0]
    assert "mã đơn hàng" in msg.texts[0]


async def test_photo_with_caption_phone(deps: Deps):
    deps.vision = FakeVisionService(
        result=VisionResult(
            tracking_codes=("840000000001",),
            carrier="J&T",
        )
    )
    # caption provides phone last4
    msg = MessageRecorder(photo=[SimpleNamespace(file_id="p1")], caption="SĐT 1234")
    update = make_update(msg)
    context = make_context(deps)

    await photo_message(update, context)
    assert len(msg.texts) == 1
    assert "840000000001" in msg.texts[0]
